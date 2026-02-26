#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据读取验证脚本 - 测试CALIPSO和H89数据读取
"""
import sys
import os
import numpy as np

# 添加父目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from src.hsd_reader import scan_h89_data, merge_blocks
from src.calipso_reader import scan_calipso_data, read_calipso_ctt

print("=" * 60)
print("数据读取验证")
print("=" * 60)

# 测试CALIPSO数据读取
print("\n1. 测试CALIPSO数据读取:")
calipso_path = "/mnt/h/CAL"
print(f"   路径: {calipso_path}")

cal_files = scan_calipso_data(calipso_path)
print(f"   找到文件数: {len(cal_files)}")

if cal_files:
    print(f"   时间范围: {cal_files[0]['datetime']} ~ {cal_files[-1]['datetime']}")

    # 测试读取第一个文件
    print("\n   测试读取第一个文件...")
    cal_data = read_calipso_ctt(cal_files[0]['filepath'], strict_mode=True)
    if cal_data:
        print(f"     总廓线数: {cal_data['total_profiles']}")
        print(f"     有效廓线数: {cal_data['valid_profiles']}")
        print(f"     CTT范围: {cal_data['ctt'].min():.2f} ~ {cal_data['ctt'].max():.2f} K")
    else:
        print("     读取失败")

# 测试H89数据读取
print("\n2. 测试H89数据读取:")
h89_path = "/mnt/h/H89"
print(f"   路径: {h89_path}")

h89_files = scan_h89_data(h89_path)
print(f"   找到时刻数: {len(h89_files)}")

if h89_files:
    print(f"   时间范围: {h89_files[0]['datetime']} ~ {h89_files[-1]['datetime']}")

    # 统计卫星分布
    sat_counts = {}
    for f in h89_files:
        sat = f['satellite']
        sat_counts[sat] = sat_counts.get(sat, 0) + 1
    print(f"   卫星分布: {sat_counts}")

    # 测试读取第一个时刻的B13数据
    print("\n   测试读取第一个时刻的B13数据...")
    first_file = h89_files[0]
    datetime_str = first_file['datetime'].strftime('%Y%m%d_%H%M')
    print(f"     时间: {datetime_str}")
    print(f"     目录: {first_file['time_dir']}")
    print(f"     卫星: {first_file['satellite']}")

    b13_data = merge_blocks(first_file['time_dir'], datetime_str, '13', first_file['satellite'])
    if b13_data is not None:
        print(f"     B13形状: {b13_data.shape}")
        print(f"     B13值域: {b13_data[~np.isnan(b13_data)].min():.2f} ~ {b13_data[~np.isnan(b13_data)].max():.2f} K")
    else:
        print("     读取失败")

print("\n" + "=" * 60)
print("验证完成")
print("=" * 60)
