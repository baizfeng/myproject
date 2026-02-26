#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
CALIPSO云顶温度数据读取模块
参考: /mnt/e/hxcode/polar/test.py
"""
import os
import numpy as np
from datetime import datetime
from glob import glob
from pyhdf.SD import SD, SDC


def parse_calipso_filename(filepath):
    """解析CALIPSO文件名，提取时间信息

    文件名格式: CAL_LID_L2_05kmCLay-Standard-V4-51.2023-01-01T04-38-40ZN.hdf

    Args:
        filepath: HDF文件路径

    Returns:
        datetime对象 或 None
    """
    try:
        basename = os.path.basename(filepath)
        # 提取时间部分: 2023-01-01T04-38-40ZN
        # 文件名格式: CAL_LID_L2_05kmCLay-Standard-V4-51.YYYY-MM-DDTHH-MM-SSZN.hdf
        # 使用正则表达式提取时间
        import re
        pattern = r'(\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2})[ZN]D?'
        match = re.search(pattern, basename)
        if match:
            time_part = match.group(1)
            dt = datetime.strptime(time_part, '%Y-%m-%dT%H-%M-%S')
            return dt
        return None
    except Exception as e:
        return None


def read_calipso_ctt(filepath, strict_mode=True):
    """读取CALIPSO云顶温度数据

    Args:
        filepath: HDF文件路径
        strict_mode: 严格模式(仅单层不透明云)

    Returns:
        dict: {
            'lat': 纬度数组,
            'lon': 经度数组,
            'ctt': 云顶温度数组,
            'cth': 云顶高度数组,
            'datetime': datetime对象
        }
        或 None(读取失败)
    """
    try:
        hdf = SD(filepath, SDC.READ)
    except Exception as e:
        return None

    try:
        # 经纬度取中心点（第1列，而非第0列）
        lat = hdf.select("Latitude")[:, 1]  # (3648,)
        lon = hdf.select("Longitude")[:, 1]  # (3648,)

        num_layers = hdf.select("Number_Layers_Found")[:, 0]  # (3648,)
        cad_score = hdf.select("CAD_Score")[:, 0]  # (3648,) 第0层
        opacity_flag = hdf.select("Opacity_Flag")[:, 0]  # (3648,) 第0层
        layer_temp = hdf.select("Layer_Top_Temperature")[:, 0]  # (3648,) 第0层
        layer_top = hdf.select("Layer_Top_Altitude")[:, 0]  # (3648,) 第0层

        dt = parse_calipso_filename(filepath)

        # 质量筛选
        # 基本筛选
        mask = (
            (num_layers >= 1)  # 有云
            & (cad_score > 20)  # 确认为云
            & (opacity_flag == 1)  # 不透明云（填充值99已被排除）
            & (layer_temp > -9999)  # 有效温度
            & (layer_top > -9999)  # 有效高度
        )

        # 严格模式：仅单层云
        if strict_mode:
            mask = mask & (num_layers == 1)

        ctt = layer_temp[mask]
        cth = layer_top[mask]
        match_lat = lat[mask]
        match_lon = lon[mask]

        return {
            'lat': match_lat,
            'lon': match_lon,
            'ctt': ctt,
            'cth': cth,
            'datetime': dt,
            'total_profiles': len(lat),
            'valid_profiles': mask.sum()
        }

    except Exception as e:
        return None
    finally:
        hdf.end()


def scan_calipso_data(base_dir):
    """扫描CALIPSO目录，获取所有可用的数据文件

    目录结构: base_dir/{YYYYMM}/ 或 base_dir/{year}/...
    实际: /mnt/h/CAL/202301/*.hdf

    Args:
        base_dir: CALIPSO数据根目录

    Returns:
        list: [{'filepath': str, 'datetime': datetime}, ...]
    """
    data_list = []

    # 检查目录结构
    # 方式1: base_dir/YYYYMM/*.hdf
    # 方式2: base_dir/year/month/day/*.hdf

    # 先尝试方式1
    for item in os.listdir(base_dir):
        item_path = os.path.join(base_dir, item)
        if os.path.isdir(item_path):
            # 检查是否是YYYYMM格式
            if len(item) == 6 and item.isdigit():
                hdf_files = glob(os.path.join(item_path, "*.hdf"))
                for f in hdf_files:
                    dt = parse_calipso_filename(f)
                    if dt:
                        data_list.append({'filepath': f, 'datetime': dt})

    # 如果方式1没有找到数据，尝试方式2
    if not data_list:
        for year in os.listdir(base_dir):
            year_path = os.path.join(base_dir, year)
            if not os.path.isdir(year_path) or not year.isdigit():
                continue

            for month in os.listdir(year_path):
                month_path = os.path.join(year_path, month)
                if not os.path.isdir(month_path) or not month.isdigit():
                    continue

                for day in os.listdir(month_path):
                    day_path = os.path.join(month_path, day)
                    if not os.path.isdir(day_path) or not day.isdigit():
                        continue

                    hdf_files = glob(os.path.join(day_path, "*.hdf"))
                    for f in hdf_files:
                        dt = parse_calipso_filename(f)
                        if dt:
                            data_list.append({'filepath': f, 'datetime': dt})

    # 按时间排序
    data_list.sort(key=lambda x: x['datetime'])

    return data_list


def get_calipso_track_bbox(lat, lon):
    """获取CALIPSO轨迹的边界框

    Args:
        lat: 纬度数组
        lon: 经度数组

    Returns:
        dict: {'lat_min', 'lat_max', 'lon_min', 'lon_max'}
    """
    return {
        'lat_min': float(np.min(lat)),
        'lat_max': float(np.max(lat)),
        'lon_min': float(np.min(lon)),
        'lon_max': float(np.max(lon))
    }


def calipso_point_to_pixel(lat, lon, lon_bounds, lat_bounds):
    """将CALIPSO点经纬度转换为等经纬度网格的像素坐标"""
    if np.isscalar(lat):
        lat = np.array([lat])
        lon = np.array([lon])

    nlat = len(lat_bounds)
    nlon = len(lon_bounds)

    # 计算经度对应的列索引
    cols = np.searchsorted(lon_bounds, lon) - 1
    cols = np.clip(cols, 0, nlon - 1)

    # 计算纬度对应的行索引 (lat_bounds是从北到南)
    rows = np.searchsorted(lat_bounds[::-1], lat) - 1
    rows = np.clip(rows, 0, nlat - 1)

    return rows, cols
