#!/usr/bin/env python3
"""
从 crates.io 的数据库 dump 生成按下载量排序的 crate 名称文件。
输出: crates-index.txt（每行一个 crate 名，第1行=下载量最高）

策略:
1. 先尝试从 crates.csv 直接读取 downloads 列
2. 如果 crates.csv 没有 downloads 列，则从 version_downloads.csv 汇总下载量
"""

import csv
import io
import os
import sys
import tarfile

# crates.csv 的 readme 列可能非常大，需要提高 CSV 字段大小限制
csv.field_size_limit(sys.maxsize)
import urllib.request
from collections import defaultdict

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
            print("tar 包内容:")
            for m in tar.getmembers():
                print(f"  {m.name}")
            sys.exit(1)

        reader = read_csv_from_tar(tar, crates_member)
        if reader is None:
            print("错误: 无法读取 crates.csv")
            sys.exit(1)

        print(f"crates.csv 列名: {reader.fieldnames}")

        # 检查是否有 downloads 列
        has_downloads = "downloads" in (reader.fieldnames or [])

        # 读取所有 crate: id -> name (以及可能的 downloads)
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

        # ========== 第二步: 如果没有 downloads 列，从其他表汇总 ==========
        if not has_downloads:
            print("crates.csv 中没有 downloads 列，尝试从 versions.csv 汇总...")

            # 先读 versions.csv 获取 version_id -> crate_id 映射，以及版本级 downloads
            versions_member = find_csv_in_tar(tar, "data/versions.csv")
            if versions_member:
                vreader = read_csv_from_tar(tar, versions_member)
                if vreader:
                    print(f"versions.csv 列名: {vreader.fieldnames}")
                    v_has_downloads = "downloads" in (vreader.fieldnames or [])
                    version_to_crate = {}

                    for row in vreader:
                        vid = row["id"]
                        cid = row["crate_id"]
                        version_to_crate[vid] = cid
                        if v_has_downloads:
                            dl = 0
                            try:
                                dl = int(row["downloads"])
                            except (ValueError, TypeError):
                                pass
                            cname = crate_id_to_name.get(cid, "")
                            if cname:
                                crate_downloads[cname] = crate_downloads.get(cname, 0) + dl

                    print(f"共读取 {len(version_to_crate)} 个版本")

            # 如果 versions.csv 也没有 downloads，尝试 version_downloads.csv
            if not crate_downloads:
                print("versions.csv 也没有 downloads，尝试 version_downloads.csv...")
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

                        # 汇总到 crate 级别
                        for vid, dl in dl_by_version.items():
                            cid = version_to_crate.get(vid, "")
                            cname = crate_id_to_name.get(cid, "")
                            if cname:
                                crate_downloads[cname] = crate_downloads.get(cname, 0) + dl

        if not crate_downloads:
            print("警告: 无法获取任何下载量数据，将按字母序排列")
            crate_downloads = {name: 0 for name in crate_id_to_name.values()}

    # ========== 第三步: 排序并输出 ==========
    sorted_crates = sorted(crate_downloads.items(), key=lambda x: x[1], reverse=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for name, _ in sorted_crates:
            out.write(name + "\n")

    print(f"\n已生成 {OUTPUT_FILE}（{len(sorted_crates)} 行）")
    print("\nTop 10:")
    for i, (name, downloads) in enumerate(sorted_crates[:10], 1):
        print(f"  {i}. {name} ({downloads:,} downloads)")


if __name__ == "__main__":
    main()