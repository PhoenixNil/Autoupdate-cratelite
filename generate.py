#!/usr/bin/env python3
"""
从 crates.io 的数据库 dump 生成按下载量排序的 crate 索引文件。
输出: crates-index.txt
格式: 每行 "crate_name latest_version"，按下载量降序排列

例:
  serde 1.0.219
  rand 0.8.5
  tokio 1.44.2
"""

import csv
import io
import os
import sys
import tarfile
import urllib.request
from collections import defaultdict

csv.field_size_limit(sys.maxsize)

DUMP_URL = "https://static.crates.io/db-dump.tar.gz"
OUTPUT_FILE = "crates-index.txt"


def find_csv_in_tar(tar, suffix):
    """在 tar 包中查找以指定后缀结尾的文件"""
    for member in tar.getmembers():
        if member.name.endswith(suffix):
            return member
    return None


def read_csv_from_tar(tar, member):
    """从 tar 包中读取 CSV 文件，返回 DictReader"""
    f = tar.extractfile(member)
    if f is None:
        return None
    return csv.DictReader(io.TextIOWrapper(f, encoding="utf-8"))


def parse_semver(version_str):
    """
    简易 semver 解析，用于比较版本号大小。
    预发布版本（含 - 如 1.0.0-alpha）排在正式版本之后。
    """
    try:
        is_prerelease = "-" in version_str
        base = version_str.split("-")[0].split("+")[0]
        parts = tuple(int(x) for x in base.split("."))
        return (1 if not is_prerelease else 0,) + parts
    except (ValueError, AttributeError):
        return (0,)


def main():
    print("下载 crates.io 数据库 dump...")
    dump_path = "db-dump.tar.gz"

    if not os.path.exists(dump_path):
        urllib.request.urlretrieve(DUMP_URL, dump_path)
        print("下载完成")
    else:
        print("使用已存在的 dump 文件")

    with tarfile.open(dump_path, "r:gz") as tar:
        # ========== 第一步: 读取 crates.csv ==========
        crates_member = find_csv_in_tar(tar, "data/crates.csv")
        if not crates_member:
            print("错误: 未找到 data/crates.csv")
            for m in tar.getmembers():
                print(f"  {m.name}")
            sys.exit(1)

        reader = read_csv_from_tar(tar, crates_member)
        if reader is None:
            print("错误: 无法读取 crates.csv")
            sys.exit(1)

        print(f"crates.csv 列名: {reader.fieldnames}")
        has_downloads = "downloads" in (reader.fieldnames or [])

        crate_id_to_name = {}
        crate_downloads = {}

        for row in reader:
            crate_id = row["id"]
            name = row["name"]
            crate_id_to_name[crate_id] = name
            if has_downloads:
                try:
                    crate_downloads[name] = int(row["downloads"])
                except (ValueError, TypeError):
                    crate_downloads[name] = 0

        print(f"共读取 {len(crate_id_to_name)} 个 crate")

        # ========== 第二步: 读取 versions.csv 获取最新版本 + 汇总下载量 ==========
        print("读取 versions.csv...")
        versions_member = find_csv_in_tar(tar, "data/versions.csv")

        latest_version = {}  # crate_id -> 最新版本号
        version_to_crate = {}

        if versions_member:
            vreader = read_csv_from_tar(tar, versions_member)
            if vreader:
                print(f"versions.csv 列名: {vreader.fieldnames}")
                v_has_downloads = "downloads" in (vreader.fieldnames or [])
                has_yanked = "yanked" in (vreader.fieldnames or [])

                for row in vreader:
                    vid = row["id"]
                    cid = row["crate_id"]
                    num = row.get("num", "")
                    yanked = row.get("yanked", "f") if has_yanked else "f"
                    version_to_crate[vid] = cid

                    # 汇总下载量（如果 crates.csv 没有）
                    if not has_downloads and v_has_downloads:
                        dl = 0
                        try:
                            dl = int(row["downloads"])
                        except (ValueError, TypeError):
                            pass
                        cname = crate_id_to_name.get(cid, "")
                        if cname:
                            crate_downloads[cname] = crate_downloads.get(cname, 0) + dl

                    # 跳过 yanked 版本
                    if yanked in ("t", "true", "True", "1"):
                        continue

                    # 记录最新非 yanked 版本
                    if num:
                        current_best = latest_version.get(cid, "")
                        if not current_best or parse_semver(num) > parse_semver(current_best):
                            latest_version[cid] = num

                print(f"共读取 {len(version_to_crate)} 个版本")
                print(f"获取到 {len(latest_version)} 个 crate 的最新版本")

        # ========== 第三步: 兜底从 version_downloads.csv 汇总 ==========
        if not crate_downloads:
            print("尝试从 version_downloads.csv 汇总下载量...")
            vd_member = find_csv_in_tar(tar, "data/version_downloads.csv")
            if vd_member:
                vd_reader = read_csv_from_tar(tar, vd_member)
                if vd_reader:
                    print(f"version_downloads.csv 列名: {vd_reader.fieldnames}")
                    dl_by_version = defaultdict(int)
                    count = 0
                    for row in vd_reader:
                        vid = row.get("version_id", "")
                        dl = 0
                        try:
                            dl = int(row.get("downloads", 0))
                        except (ValueError, TypeError):
                            pass
                        dl_by_version[vid] += dl
                        count += 1
                        if count % 5_000_000 == 0:
                            print(f"  已处理 {count:,} 行...")

                    print(f"共处理 {count:,} 行下载记录")
                    for vid, dl in dl_by_version.items():
                        cid = version_to_crate.get(vid, "")
                        cname = crate_id_to_name.get(cid, "")
                        if cname:
                            crate_downloads[cname] = crate_downloads.get(cname, 0) + dl

        if not crate_downloads:
            print("警告: 无法获取任何下载量数据，将按字母序排列")
            crate_downloads = {name: 0 for name in crate_id_to_name.values()}

    # ========== 第四步: 排序并输出（含版本号）==========
    name_to_id = {v: k for k, v in crate_id_to_name.items()}
    sorted_crates = sorted(crate_downloads.items(), key=lambda x: x[1], reverse=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for name, _ in sorted_crates:
            cid = name_to_id.get(name, "")
            version = latest_version.get(cid, "0.0.0")
            out.write(f"{name} {version}\n")

    print(f"\n已生成 {OUTPUT_FILE}（{len(sorted_crates)} 行）")
    print("\nTop 10:")
    for i, (name, downloads) in enumerate(sorted_crates[:10], 1):
        cid = name_to_id.get(name, "")
        version = latest_version.get(cid, "?")
        print(f"  {i}. {name} {version} ({downloads:,} downloads)")


if __name__ == "__main__":
    main()