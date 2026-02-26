#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
时空匹配模块 - CALIPSO与葵花卫星数据匹配
参考: /mnt/e/code/smart3_project/arspy/space_match.py
"""
import os
import numpy as np
import pandas as pd
import rioxarray as rxr


def match_temporal_spatial(calipso_data, h89_data, time_window_minutes=15):
    """时空匹配CALIPSO和H89数据"""
    matches = []
    h89_by_datetime = {item['datetime']: item for item in h89_data}

    for cal_item in calipso_data:
        cal_time = cal_item['datetime']
        matching_h89 = []
        for h89_time, h89_item in h89_by_datetime.items():
            time_diff = abs((cal_time - h89_time).total_seconds())
            if time_diff <= time_window_minutes * 60:
                matching_h89.append({'item': h89_item, 'time_diff': time_diff})

        if not matching_h89:
            continue

        matching_h89.sort(key=lambda x: x['time_diff'])
        best_h89 = matching_h89[0]

        matches.append({
            'calipso': cal_item,
            'h89': best_h89['item'],
            'time_diff_sec': best_h89['time_diff']
        })

    return matches


def space_match(tif_data, lon_arr, lat_arr):
    """空间匹配 - 从重投影的TIFF数据中提取指定经纬度点的值
    参考: /mnt/e/code/smart3_project/arspy/space_match.py spaceMatch函数
    """
    band = tif_data.sel(band=1)
    band = band.rename({'x': 'longitude', 'y': 'latitude'})
    band_interp = band.interp(longitude=lon_arr, latitude=lat_arr, method="nearest")
    return band_interp.values


def extract_matched_data(calipso_obj, reproj_bands, lon_bounds, lat_bounds):
    """从匹配的数据对中提取匹配点数据"""
    lat = calipso_obj['lat']
    lon = calipso_obj['lon']
    ctt = calipso_obj['ctt']
    cth = calipso_obj['cth']

    # 将numpy数组转为xarray.DataArray以支持interp
    import xarray as xr
    tb13_data = xr.DataArray(reproj_bands['B13'],
                              dims=('latitude', 'longitude'),
                              coords={'latitude': lat_bounds, 'longitude': lon_bounds})
    tb15_data = xr.DataArray(reproj_bands['B15'],
                              dims=('latitude', 'longitude'),
                              coords={'latitude': lat_bounds, 'longitude': lon_bounds})

    # 使用interp提取对应位置的值 (使用nearest方法)
    tb13_interp = tb13_data.interp(longitude=lon, latitude=lat, method="nearest")
    tb15_interp = tb15_data.interp(longitude=lon, latitude=lat, method="nearest")

    # interp返回2D数组，取对角线元素
    tb13_values = np.diag(tb13_interp.values)
    tb15_values = np.diag(tb15_interp.values)

    # 构建DataFrame
    matched_df = pd.DataFrame({
        'lat': lat, 'lon': lon, 'ctt': ctt, 'cth': cth,
        'tb13': tb13_values, 'tb15': tb15_values,
        'calipso_time': [calipso_obj['datetime']] * len(lat)
    })

    # 移除无效值
    matched_df = matched_df[
        (matched_df['tb13'] > 0) & (matched_df['tb15'] > 0) &
        (np.isfinite(matched_df['tb13'])) & (np.isfinite(matched_df['tb15']))
    ]

    return matched_df


def quality_control(df, tb_min=180.0, tb_max=340.0, ctt_min=180.0, ctt_max=340.0,
                    zenith_max=80.0, tb_diff_min=-5.0, tb_diff_max=10.0):
    """数据质量控制"""
    tb13_valid = (df['tb13'] >= tb_min) & (df['tb13'] <= tb_max)
    tb15_valid = (df['tb15'] >= tb_min) & (df['tb15'] <= tb_max)
    ctt_valid = (df['ctt'] >= ctt_min) & (df['ctt'] <= ctt_max)
    tb_diff = df['tb13'] - df['tb15']
    tb_diff_valid = (tb_diff >= tb_diff_min) & (tb_diff <= tb_diff_max)
    finite_valid = (np.isfinite(df['tb13']) & np.isfinite(df['tb15']) &
                   np.isfinite(df['ctt']))

    qc_mask = tb13_valid & tb15_valid & ctt_valid & tb_diff_valid & finite_valid
    df_qc = df[qc_mask].copy()
    df_qc['tb_diff'] = df_qc['tb13'] - df_qc['tb15']
    df_qc['tb_bias'] = df_qc['tb13'] - df_qc['ctt']

    return df_qc


def match_all_data(calipso_files, h89_files, time_window_minutes=15,
                   sat_lon=140.7, output_bounds=(55.0, -85.0, 225.0, 85.0),
                   res=0.02, progress_callback=None):
    """匹配所有CALIPSO和H89数据"""
    from .calipso_reader import read_calipso_ctt
    from .hsd_reader import read_h89_bands, reproject_bands_to_latlon

    # 时间匹配
    matches = match_temporal_spatial(calipso_files, h89_files, time_window_minutes)
    if not matches:
        return pd.DataFrame()

    # 提取匹配数据
    all_matched_data = []

    for i, match in enumerate(matches):
        calipso_obj = read_calipso_ctt(match['calipso']['filepath'], strict_mode=True)
        if calipso_obj is None:
            continue

        datetime_str = match['h89']['datetime'].strftime('%Y%m%d_%H%M')
        h89_bands = read_h89_bands(match['h89']['time_dir'], datetime_str,
                                   match['h89']['satellite'], bands=['13', '15'])
        if h89_bands is None:
            continue

        # 重投影到等经纬度
        reproj_bands, lon_bounds, lat_bounds = reproject_bands_to_latlon(
            h89_bands, sat_lon, output_bounds, res
        )

        # 提取匹配点
        matched_df = extract_matched_data(calipso_obj, reproj_bands, lon_bounds, lat_bounds)

        if len(matched_df) > 0:
            matched_df['h89_time'] = match['h89']['datetime']
            matched_df['time_diff_sec'] = match['time_diff_sec']
            matched_df['sat_zenith'] = np.nan  # 暂时设为nan，后续可添加天顶角处理
            all_matched_data.append(matched_df)

        if progress_callback:
            progress_callback(i + 1, len(matches))

    return pd.concat(all_matched_data, ignore_index=True) if all_matched_data else pd.DataFrame()
