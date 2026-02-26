#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
文件命名解析与生成模块
"""

import re
import os
from datetime import datetime, timedelta


def parse_name(filename, pattern):
    """解析输入文件名，返回字段字典"""
    basename = os.path.basename(filename)
    match = re.match(pattern, basename)
    if match:
        return match.groupdict()
    return None


def build_names(params, template, formats, rootpath, **extra):
    """生成所有格式的输出文件路径字典，并创建目录

    参数:
        params: 解析得到的字段字典
        template: 输出文件名模板
        formats: 输出格式列表，如 ["NC", "TIFF"] 或 ["NC", "TIFF:IR11/IR12"]
        rootpath: 输出根路径
        **extra: 额外字段

    返回:
        dict: 以格式名为键的路径字典，如 {"NC": "...", "TIFF:IR11/IR12": "..."}
    """
    # 从模板中提取需要的字段
    fields = re.findall(r'\{(\w+)\}', template)

    # 检查是否有波段定义
    has_band = any(':' in f for f in formats)

    results = {}
    for fmt in formats:
        # 解析格式和波段
        if ':' in fmt:
            fmt_type, bands = fmt.split(':', 1)
            band_list = bands.split('/')
        else:
            fmt_type = fmt
            band_list = None

        # 跳过独立PNG（当有波段定义时）
        if fmt_type == "PNG" and has_band:
            continue

        # 合并参数：params + extra
        kwargs = {**params, **extra}
        kwargs['format'] = fmt_type
        kwargs['rootpath'] = rootpath

        # 检查缺少的字段
        missing = [f for f in fields if f not in kwargs]
        if missing:
            raise ValueError(f"缺少字段: {missing}")

        output_path = template.format(**kwargs)
        results[fmt_type] = output_path

        # 创建目录
        dir_path = os.path.dirname(output_path)
        os.makedirs(dir_path, exist_ok=True)

        # 有波段定义时，额外生成波段PNG
        if band_list and "PNG" in formats:
            base_path = output_path.rsplit('.', 1)[0]
            for band in band_list:
                png_key = f"PNG.{band}"
                results[png_key] = f"{base_path}.{band}.PNG"

    return results


def build_mapinfo(params, bands=None, titles=None):
    """生成绘图mapinfo信息

    参数:
        params: 解析得到的字段字典，需包含 yyyymmdd, HHMMSS, resolution, satellite, sensor
        bands: 波段列表，如 ['IR11', 'IR12']，如果为None则返回单个mapinfo
        titles: 标题字典、列表或单个字符串
               - 单个mapinfo时: 直接传标题字符串，如 "产品标题"
               - 多波段时: {'IR11': '标题1', 'IR12': '标题2'} 或 ['标题1', '标题2']

    返回:
        dict: mapinfo字典，键为 'IR11mapinfo', 'IR12mapinfo' 等
    """
    if titles is None:
        raise ValueError("titles参数不能为None，必须传入标题")

    ymd = params.get('yyyymmdd', '')
    hhmm = params.get('HHMMSS', '')
    # 文件名是世界时，加8小时转换为北京时
    dt = datetime.strptime(f"{ymd}{hhmm}", "%Y%m%d%H%M%S") + timedelta(hours=8)
    date_str = dt.strftime("%Y年%m月%d日 %H:%M:%S(北京时)")

    # 格式化分辨率: 0500M -> 500m
    res = params.get('resolution', '').replace('M', 'm').lstrip('0') or '0m'
    if res.endswith('m') and res[:-1].isdigit():
        res_num = res[:-1]
        res = f"{res_num}m"

    sat_sensor = f"数据源:{params.get('satellite', '')}/{params.get('sensor', '')}"

    if bands is None:
        # 返回单个mapinfo
        return {
            "title": titles,
            "date": date_str,
            "sat_sensor": sat_sensor,
            "res": f"空间分辨率:{res}"
        }

    # 处理titles参数：列表转为字典
    if isinstance(titles, list):
        titles = {band: title for band, title in zip(bands, titles)}
    elif isinstance(titles, str):
        # 单个字符串用于所有波段
        titles = {band: titles for band in bands}

    # 返回多个波段的mapinfo
    result = {}
    for band in bands:
        if band not in titles:
            raise ValueError(f"缺少波段 {band} 的标题")
        result[f"{band}"] = {
            "title": titles[band],
            "date": date_str,
            "sat_sensor": sat_sensor,
            "res": f"空间分辨率:{res}"
        }

    return result
