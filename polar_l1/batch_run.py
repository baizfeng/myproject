#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
批量处理脚本 - 处理HDF数据
简洁版: 使用os.system调用
"""
import os
import sys
import re
from pathlib import Path
from datetime import datetime

# ==================== 配置参数 ====================
INPUT_DIR = r"/mnt/f/YH1C202504/L1/IRSR"  # 输入数据目录
OUTPUT_DIR = r"/mnt/g/product"  # 输出目录
LOG_DIR = r"/mnt/g/logs"  # 日志目录


AUX_PATH = r"/mnt/d/auxdata/polar"  # 辅助数据路径

# 输入文件命名模式
INPUT_PATTERN = re.compile(r"[^_]+_[^_]+_[^_]+_\d{8}_\d{6}_R\d+M_L1\.hdf")


def find_geo_file(primary_file):
    """查找对应的GEO文件 - 直接字符串替换"""
    path_obj = Path(primary_file)
    # BEI_YH1C_IRSR_20250401_000943_R0500M_L1.hdf -> BEI_YH1C_IRSR_20250401_000943_GEO_L1.hdf
    # 替换 _R0500M_ 为 _GEO_
    geo_name = path_obj.name.replace("_R0500M_", "_GEO_")
    geo_file = path_obj.parent / geo_name
    if geo_file.exists():
        return str(geo_file)
    return None


def run_job(primary_file, geo_file):
    """执行单个任务 - 使用os.system调用"""
    path_obj = Path(primary_file)

    # 解析日期

    # 创建目录 - 统一使用正斜杠
    output_dir = f"{OUTPUT_DIR}/"
    log_dir = f"{LOG_DIR}/{path_obj.stem}"
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(log_dir, exist_ok=True)

    # 路径转正斜杠（Windows兼容）
    primary_file_fixed = str(primary_file).replace("\\", "/")
    geo_file_fixed = str(geo_file).replace("\\", "/")
    log_dir_fixed = log_dir.replace("\\", "/")

    # 创建输入JSON
    json_file = f"{log_dir}/input.json"
    json_content = f"""{{
  "primaryFile": "{primary_file_fixed}",
  "geoFile": "{geo_file_fixed}",
  "resultPath": "{output_dir}",
  "auxPath": "{AUX_PATH}",
  "resultJsonFile": "{log_dir_fixed}/result.json",
  "resultLogFile": "{log_dir_fixed}/log.log",
  "resultFlowFile": "{log_dir_fixed}/flow.json"
}}"""

    with open(json_file, "w") as f:
        f.write(json_content)

    # 调用: python app.py input.json
    cmd = f"python {os.path.dirname(__file__)}/app.py {json_file}"
    print(f"执行: {cmd}")
    return os.system(cmd)


def main():
    """批量处理主函数"""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    os.makedirs(LOG_DIR, exist_ok=True)

    input_path = Path(INPUT_DIR)
    if not input_path.exists():
        print(f"错误: 输入目录不存在: {INPUT_DIR}")
        return

    # 递归查找IRSR文件（包括子目录）
    hdf_files = list(input_path.rglob("*.hdf"))
    primary_files = [
        f for f in hdf_files if INPUT_PATTERN.match(f.name) and "IRSR" in f.name
    ]

    print(f"找到 {len(primary_files)} 个待处理文件")

    success = 0
    failed = 0

    for primary_file in primary_files:
        print(f"\n处理: {primary_file.name}")

        geo_file = find_geo_file(str(primary_file))
        if not geo_file:
            print(f"  跳过: 未找到GEO文件")
            failed += 1
            continue

        ret = run_job(str(primary_file), geo_file)
        if ret == 0:
            print(f"  成功")
            success += 1
        else:
            print(f"  失败")
            failed += 1

    print(f"\n处理完成: 成功={success}, 失败={failed}")


if __name__ == "__main__":
    main()
