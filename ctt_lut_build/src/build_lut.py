#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
查找表构建模块
基于匹配后的数据构建(TB13, TB15, 天顶角) -> CTT查找表
"""
import os
import numpy as np
import pandas as pd


# 查找表网格配置
TB13_BINS = np.arange(180, 341, 2)   # B13亮温: 180-340K, 步长2K
TB15_BINS = np.arange(180, 341, 2)   # B15亮温: 180-340K, 步长2K
ZENITH_BINS = np.arange(0, 81, 5)    # 天顶角: 0-80度, 步长5度


def create_lut_bins(df):
    """将数据离散化到查找表网格

    Args:
        df: 质量控制后的匹配数据DataFrame

    Returns:
        DataFrame: 添加了bin列的数据
    """
    # 离散化
    df['tb13_bin'] = pd.cut(df['tb13'], bins=TB13_BINS)
    df['tb15_bin'] = pd.cut(df['tb15'], bins=TB15_BINS)
    df['zenith_bin'] = pd.cut(df['sat_zenith'], bins=ZENITH_BINS)

    return df


def build_lut(df_lut, min_samples=10):
    """构建查找表

    Args:
        df_lut: 离散化后的数据
        min_samples: 最小样本数阈值

    Returns:
        DataFrame: 查找表
    """
    # 按网格分组统计
    grouped = df_lut.groupby(['tb13_bin', 'tb15_bin', 'zenith_bin'], observed=True).agg({
        'ctt': ['mean', 'std', 'count', lambda x: np.sqrt(((x - x.mean()) ** 2).mean())]
    }).reset_index()

    grouped.columns = ['tb13_bin', 'tb15_bin', 'zenith_bin', 'ctt_mean', 'ctt_std', 'count', 'ctt_rmse']

    # 提取bin中心值
    grouped['tb13_center'] = grouped['tb13_bin'].apply(lambda x: x.mid if hasattr(x, 'mid') else np.nan)
    grouped['tb15_center'] = grouped['tb15_bin'].apply(lambda x: x.mid if hasattr(x, 'mid') else np.nan)
    grouped['zenith_center'] = grouped['zenith_bin'].apply(lambda x: x.mid if hasattr(x, 'mid') else np.nan)

    # 设置最小样本数阈值
    grouped_valid = grouped[grouped['count'] >= min_samples].copy()

    return grouped_valid


def create_grid_lut(lut_df):
    """创建完整的网格化查找表（包含空值填充）

    Args:
        lut_df: 有效网格数据

    Returns:
        DataFrame: 完整网格查找表
    """
    # 创建所有组合的网格
    tb13_centers = [(TB13_BINS[i] + TB13_BINS[i+1]) / 2 for i in range(len(TB13_BINS)-1)]
    tb15_centers = [(TB15_BINS[i] + TB15_BINS[i+1]) / 2 for i in range(len(TB15_BINS)-1)]
    zenith_centers = [(ZENITH_BINS[i] + ZENITH_BINS[i+1]) / 2 for i in range(len(ZENITH_BINS)-1)]

    grid_list = []

    for tb13 in tb13_centers:
        for tb15 in tb15_centers:
            for zenith in zenith_centers:
                grid_list.append({
                    'tb13_center': tb13,
                    'tb15_center': tb15,
                    'zenith_center': zenith
                })

    grid_df = pd.DataFrame(grid_list)

    # 合并统计值
    grid_lut = grid_df.merge(
        lut_df[['tb13_center', 'tb15_center', 'zenith_center',
                'ctt_mean', 'ctt_std', 'count', 'ctt_rmse']],
        on=['tb13_center', 'tb15_center', 'zenith_center'],
        how='left'
    )

    return grid_lut


def interpolate_missing_lut(grid_lut):
    """对缺失值进行插值填充

    Args:
        grid_lut: 网格化查找表

    Returns:
        DataFrame: 插值后的查找表
    """
    lut_interpolated = grid_lut.copy()

    # 添加插值标记
    lut_interpolated['interpolated'] = False

    # 对每个天顶角分别处理
    for zenith in lut_interpolated['zenith_center'].unique():
        if pd.isna(zenith):
            continue

        lut_zenith = lut_interpolated[lut_interpolated['zenith_center'] == zenith].copy()

        # 创建透视表
        pivot = lut_zenith.pivot_table(
            index='tb13_center',
            columns='tb15_center',
            values='ctt_mean'
        )

        # 插值
        pivot_interp = pivot.interpolate(method='linear', axis=0).interpolate(method='linear', axis=1)

        # 边缘填充
        pivot_interp = pivot_interp.fillna(method='bfill', axis=0).fillna(method='ffill', axis=0)
        pivot_interp = pivot_interp.fillna(method='bfill', axis=1).fillna(method='ffill', axis=1)

        # 更新回lut
        for tb13 in pivot_interp.index:
            for tb15 in pivot_interp.columns:
                mask = (lut_interpolated['tb13_center'] == tb13) & \
                       (lut_interpolated['tb15_center'] == tb15) & \
                       (lut_interpolated['zenith_center'] == zenith)
                if mask.any():
                    if pd.isna(lut_interpolated.loc[mask, 'ctt_mean'].values[0]):
                        lut_interpolated.loc[mask, 'ctt_mean'] = pivot_interp.loc[tb13, tb15]
                        lut_interpolated.loc[mask, 'interpolated'] = True

    return lut_interpolated


def save_lut(lut_final, output_dir):
    """保存查找表

    Args:
        lut_final: 最终查找表
        output_dir: 输出目录

    Returns:
        dict: 保存的文件路径
    """
    os.makedirs(output_dir, exist_ok=True)

    # 选择输出列
    output_cols = [
        'tb13_center', 'tb15_center', 'zenith_center',
        'ctt_mean', 'ctt_std', 'count', 'ctt_rmse', 'interpolated'
    ]

    lut_out = lut_final[output_cols].copy()
    lut_out = lut_out.rename(columns={
        'tb13_center': 'tb13',
        'tb15_center': 'tb15',
        'zenith_center': 'sat_zenith',
        'ctt_mean': 'ctt',
        'ctt_std': 'ctt_std',
        'count': 'sample_count',
        'ctt_rmse': 'ctt_rmse'
    })

    # 保存完整查找表
    lut_file = os.path.join(output_dir, 'ctt_lut_full.csv')
    lut_out.to_csv(lut_file, index=False)

    # 保存有效数据查找表（只保留有原始数据的）
    lut_valid = lut_out[lut_out['sample_count'].notna()].copy()
    lut_valid_file = os.path.join(output_dir, 'ctt_lut_valid.csv')
    lut_valid.to_csv(lut_valid_file, index=False)

    # 保存NetCDF格式 (可选)
    try:
        import xarray as xr

        # 转换为xarray Dataset
        tb13_unique = sorted(lut_out['tb13'].unique())
        tb15_unique = sorted(lut_out['tb15'].unique())
        zenith_unique = sorted(lut_out['sat_zenith'].unique())

        # 创建3D数组
        ctt_3d = np.full((len(zenith_unique), len(tb13_unique), len(tb15_unique)), np.nan)
        std_3d = np.full((len(zenith_unique), len(tb13_unique), len(tb15_unique)), np.nan)
        count_3d = np.full((len(zenith_unique), len(tb13_unique), len(tb15_unique)), np.nan)
        rmse_3d = np.full((len(zenith_unique), len(tb13_unique), len(tb15_unique)), np.nan)

        for _, row in lut_out.iterrows():
            i = zenith_unique.index(row['sat_zenith'])
            j = tb13_unique.index(row['tb13'])
            k = tb15_unique.index(row['tb15'])
            ctt_3d[i, j, k] = row['ctt']
            if not pd.isna(row['ctt_std']):
                std_3d[i, j, k] = row['ctt_std']
            if not pd.isna(row['sample_count']):
                count_3d[i, j, k] = row['sample_count']
            if not pd.isna(row['ctt_rmse']):
                rmse_3d[i, j, k] = row['ctt_rmse']

        ds = xr.Dataset({
            'ctt': (['sat_zenith', 'tb13', 'tb15'], ctt_3d),
            'ctt_std': (['sat_zenith', 'tb13', 'tb15'], std_3d),
            'sample_count': (['sat_zenith', 'tb13', 'tb15'], count_3d),
            'ctt_rmse': (['sat_zenith', 'tb13', 'tb15'], rmse_3d),
        }, coords={
            'sat_zenith': zenith_unique,
            'tb13': tb13_unique,
            'tb15': tb15_unique
        })

        # 添加属性
        ds.attrs['title'] = 'Cloud Top Temperature Lookup Table'
        ds.attrs['source'] = 'CALIPSO + Himawari-8/9'
        ds.attrs['tb13_units'] = 'Kelvin'
        ds.attrs['tb15_units'] = 'Kelvin'
        ds.attrs['sat_zenith_units'] = 'degrees'
        ds.attrs['ctt_units'] = 'Kelvin'

        nc_file = os.path.join(output_dir, 'ctt_lut.nc')
        ds.to_netcdf(nc_file)

    except ImportError:
        nc_file = None

    return {
        'lut_full': lut_file,
        'lut_valid': lut_valid_file,
        'lut_netcdf': nc_file
    }


def generate_lut_statistics(lut_final):
    """生成查找表统计信息

    Args:
        lut_final: 最终查找表

    Returns:
        dict: 统计信息
    """
    lut_valid = lut_final[lut_final['sample_count'].notna()]

    stats = {
        'total_grids': len(lut_final),
        'valid_grids': len(lut_valid),
        'coverage_rate': len(lut_valid) / len(lut_final) * 100 if len(lut_final) > 0 else 0,
        'ctt_range': (lut_valid['ctt_mean'].min(), lut_valid['ctt_mean'].max()) if len(lut_valid) > 0 else (np.nan, np.nan),
        'ctt_mean': lut_valid['ctt_mean'].mean() if len(lut_valid) > 0 else np.nan,
        'rmse_mean': lut_valid['ctt_rmse'].mean() if len(lut_valid) > 0 else np.nan,
        'total_samples': lut_valid['count'].sum() if len(lut_valid) > 0 else 0
    }

    return stats


def build_lut_from_matched_data(matched_df, output_dir, min_samples=10, do_interpolate=True):
    """从匹配数据构建查找表

    Args:
        matched_df: 质量控制后的匹配数据
        output_dir: 输出目录
        min_samples: 最小样本数阈值
        do_interpolate: 是否进行插值

    Returns:
        dict: 查找表和统计信息
    """
    # 离散化
    df_lut = create_lut_bins(matched_df)

    # 构建查找表
    lut_valid = build_lut(df_lut, min_samples=min_samples)

    # 创建完整网格
    grid_lut = create_grid_lut(lut_valid)

    # 插值
    if do_interpolate:
        lut_final = interpolate_missing_lut(grid_lut)
    else:
        lut_final = grid_lut.copy()

    # 保存查找表
    saved_files = save_lut(lut_final, output_dir)

    # 生成统计信息
    stats = generate_lut_statistics(lut_final)

    return {
        'lut': lut_final,
        'saved_files': saved_files,
        'statistics': stats
    }
