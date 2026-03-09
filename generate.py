#!/usr/bin/env python3
"""
从 crates.io 的数据库 dump 生成按下载量排序的 crate 名称文件。
输出: crates-index.txt（每行一个 crate 名，第1行=下载量最高）
"""

import csv
import io
import os
import tarfile
import urllib.request

DUMP_URL = "https://static.crates.io/db-dump.tar.gz"
OUTPUT_FILE = "crates-index.txt"


def main():
    print("下载 crates.io 数据库 dump...")
    dump_path = "db-dump.tar.gz"

    # 下载（约 300MB，需要几分钟）
    if not os.path.exists(dump_path):
        urllib.request.urlretrieve(DUMP_URL, dump_path)
        print("下载完成")
    else:
        print("使用已存在的 dump 文件")

    print("解析 crates.csv...")
    crates = []

    with tarfile.open(dump_path, "r:gz") as tar:
        # 找到 data/crates.csv
        for member in tar.getmembers():
            if member.name.endswith("/data/crates.csv"):
                f = tar.extractfile(member)
                if f is None:
                    continue
                text = io.TextIOWrapper(f, encoding="utf-8")
                reader = csv.DictReader(text)
                for row in reader:
                    name = row["name"]
                    downloads = int(row["downloads"])
                    crates.append((name, downloads))
                break

    print(f"共解析 {len(crates)} 个 crate")

    # 按下载量降序排序
    crates.sort(key=lambda x: x[1], reverse=True)

    # 只输出名称，行号即排名
    with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
        for name, _ in crates:
            out.write(name + "\n")

    print(f"已生成 {OUTPUT_FILE}（{len(crates)} 行）")

    # 打印前10验证
    print("\nTop 10:")
    for i, (name, downloads) in enumerate(crates[:10], 1):
        print(f"  {i}. {name} ({downloads:,} downloads)")


if __name__ == "__main__":
    main()
