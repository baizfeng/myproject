#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
算法主文件 - 云顶温度查找表建立
使用CALIPSO云顶温度和葵花卫星(H8/H9)亮温数据构建CTT查找表
"""
import os
import numpy as np
import pandas as pd
from datetime import datetime
import json

from arspy import log

# 导入自定义模块
from .hsd_reader import scan_h89_data
from .calipso_reader import scan_calipso_data
from .match_data import match_all_data, quality_control
from .build_lut import build_lut_from_matched_data


def main(primaryPath, himawariPath, resultPath, auxPath):
    """主算法函数

    Args:
        primaryPath: CALIPSO数据路径 (/mnt/h/CAL)
        himawariPath: 葵花卫星数据路径 (/mnt/h/H89)
        resultPath: 结果输出路径 (/mnt/e/output/polar)
        auxPath: 辅助数据路径 (/mnt/d/auxdata/polar)
    """
    log("=" * 60)
    log("云顶温度查找表构建算法")
    log("=" * 60)

    # 创建输出目录
    os.makedirs(resultPath, exist_ok=True)

    # 设置辅助数据路径
    # 天顶角: /mnt/d/auxdata/polar_satellite/AHI9_OBI_2000M_GLL_SZA.TIFF
    zenith_path = os.path.join(auxPath, "AHI9_OBI_2000M_GLL_SZA.TIFF") if auxPath else None
    if zenith_path and not os.path.exists(zenith_path):
        zenith_path = None

    # 步骤1: 数据扫描
    log("\n步骤1: 数据扫描")
    log(f"  CALIPSO数据路径: {primaryPath}")
    log(f"  葵花卫星数据路径: {himawariPath}")
    log(f"  结果输出路径: {resultPath}")
    log(f"  辅助数据路径: {auxPath}")

    # 扫描CALIPSO数据
    log("  正在扫描CALIPSO数据...")
    calipso_files = scan_calipso_data(primaryPath)
    log(f"  找到CALIPSO文件数: {len(calipso_files)}")

    if not calipso_files:
        log("  错误: 未找到CALIPSO数据!")
        return

    # 扫描H89数据
    log("  正在扫描葵花卫星数据...")
    h89_files = scan_h89_data(himawariPath)
    log(f"  找到葵花卫星时刻数: {len(h89_files)}")

    if not h89_files:
        log("  错误: 未找到葵花卫星数据!")
        return

    # 显示时间范围
    cal_times = [f['datetime'] for f in calipso_files]
    h89_times = [f['datetime'] for f in h89_files]

    log(f"  CALIPSO时间范围: {min(cal_times)} ~ {max(cal_times)}")
    log(f"  葵花卫星时间范围: {min(h89_times)} ~ {max(h89_times)}")

    # 统计卫星分布
    sat_counts = {}
    for f in h89_files:
        sat = f['satellite']
        sat_counts[sat] = sat_counts.get(sat, 0) + 1
    log(f"  葵花卫星分布: H08={sat_counts.get('H08', 0)}, H09={sat_counts.get('H09', 0)}")

    # 保存扫描结果
    scan_result = {
        'calipso_files': len(calipso_files),
        'calipso_time_start': str(min(cal_times)),
        'calipso_time_end': str(max(cal_times)),
        'h89_files': len(h89_files),
        'h89_time_start': str(min(h89_times)),
        'h89_time_end': str(max(h89_times)),
        'h08_count': sat_counts.get('H08', 0),
        'h09_count': sat_counts.get('H09', 0)
    }
    scan_file = os.path.join(resultPath, 'step0_scan_result.json')
    with open(scan_file, 'w', encoding='utf-8') as f:
        json.dump(scan_result, f, indent=2, ensure_ascii=False)
    log(f"  扫描结果已保存: {scan_file}")

    # 步骤2: 时空匹配
    log("\n步骤2: 时空匹配")
    log("  正在进行时空匹配(时间窗口: 15分钟)...")
    log("  将葵花卫星数据从全圆盘投影转换为等经纬度投影...")

    # 定义进度回调
    def progress_callback(current, total):
        if current % 10 == 0 or current == total:
            log(f"    进度: {current}/{total} ({current/total*100:.1f}%)")

    matched_df = match_all_data(
        calipso_files,
        h89_files,
        time_window_minutes=15,
        sat_lon=140.7,
        output_bounds=(55.0, -85.0, 225.0, 85.0),
        res=0.02,
        progress_callback=progress_callback
    )

    if matched_df is None or len(matched_df) == 0:
        log("  警告: 未找到匹配数据!")
        return

    log(f"  匹配点数: {len(matched_df):,}")
    log(f"  时间差统计: min={matched_df['time_diff_sec'].min():.0f}s, "
        f"max={matched_df['time_diff_sec'].max():.0f}s, "
        f"mean={matched_df['time_diff_sec'].mean():.0f}s")

    # 保存匹配数据
    matched_file = os.path.join(resultPath, 'step1_matched_data.csv')
    matched_df.to_csv(matched_file, index=False)
    log(f"  匹配数据已保存: {matched_file}")

    # 步骤3: 质量控制
    log("\n步骤3: 质量控制")
    log("  正在进行数据质量控制...")

    initial_count = len(matched_df)
    qc_df = quality_control(matched_df)
    qc_count = len(qc_df)

    log(f"  初始数据量: {initial_count:,}")
    log(f"  QC后数据量: {qc_count:,} ({qc_count/initial_count*100:.2f}%)")
    log(f"  剔除数据量: {initial_count - qc_count:,} ({(initial_count - qc_count)/initial_count*100:.2f}%)")

    if qc_count == 0:
        log("  错误: 质量控制后无有效数据!")
        return

    # 数据统计
    log(f"  数据统计:")
    log(f"    TB13: {qc_df['tb13'].mean():.2f} +/- {qc_df['tb13'].std():.2f} K "
        f"({qc_df['tb13'].min():.2f} ~ {qc_df['tb13'].max():.2f})")
    log(f"    TB15: {qc_df['tb15'].mean():.2f} +/- {qc_df['tb15'].std():.2f} K "
        f"({qc_df['tb15'].min():.2f} ~ {qc_df['tb15'].max():.2f})")
    log(f"    CTT:  {qc_df['ctt'].mean():.2f} +/- {qc_df['ctt'].std():.2f} K "
        f"({qc_df['ctt'].min():.2f} ~ {qc_df['ctt'].max():.2f})")
    log(f"    TB13-CTT bias: {(qc_df['tb13'] - qc_df['ctt']).mean():.2f} K")
    log(f"    卫星天顶角: {qc_df['sat_zenith'].mean():.2f} +/- {qc_df['sat_zenith'].std():.2f} 度")

    # 保存QC数据
    qc_file = os.path.join(resultPath, 'step2_qc_data.csv')
    qc_df.to_csv(qc_file, index=False)
    log(f"  QC数据已保存: {qc_file}")

    # 步骤4: 构建查找表
    log("\n步骤4: 构建查找表")
    log("  正在构建查找表...")

    result = build_lut_from_matched_data(
        qc_df,
        output_dir=resultPath,
        min_samples=10,
        do_interpolate=True
    )

    # 显示查找表文件
    log("  查找表已生成:")
    log(f"    完整查找表: {result['saved_files']['lut_full']}")
    log(f"    有效数据查找表: {result['saved_files']['lut_valid']}")
    if result['saved_files']['lut_netcdf']:
        log(f"    NetCDF格式: {result['saved_files']['lut_netcdf']}")

    # 显示统计信息
    stats = result['statistics']
    log(f"\n  查找表统计:")
    log(f"    总网格数: {stats['total_grids']:,}")
    log(f"    有效网格数: {stats['valid_grids']:,}")
    log(f"    覆盖率: {stats['coverage_rate']:.2f}%")
    log(f"    总样本数: {stats['total_samples']:,}")
    log(f"    CTT范围: {stats['ctt_range'][0]:.2f} ~ {stats['ctt_range'][1]:.2f} K")
    log(f"    平均RMSE: {stats['rmse_mean']:.2f} K")

    # 步骤5: 验证报告
    log("\n步骤5: 验证报告")

    # 计算验证统计
    validation_stats = {
        'tb13_ctt_bias': float((qc_df['tb13'] - qc_df['ctt']).mean()),
        'tb13_ctt_rmse': float(np.sqrt(((qc_df['tb13'] - qc_df['ctt']) ** 2).mean())),
        'tb13_ctt_corr': float(qc_df['tb13'].corr(qc_df['ctt'])),
        'lut_ctt_bias': float(np.nan),  # 将在应用LUT后计算
        'lut_ctt_rmse': float(np.nan),
    }

    # 按CTT范围分组统计
    ctt_bins = [180, 200, 220, 240, 260, 280, 300, 320, 340]
    qc_df_temp = qc_df.copy()
    qc_df_temp['ctt_bin'] = pd.cut(qc_df_temp['ctt'], bins=ctt_bins)

    bin_stats = []
    for bin_range, group in qc_df_temp.groupby('ctt_bin'):
        if len(group) > 0:
            bin_stats.append({
                'ctt_range': str(bin_range),
                'count': len(group),
                'tb13_ctt_bias': float((group['tb13'] - group['ctt']).mean()),
                'tb13_ctt_rmse': float(np.sqrt(((group['tb13'] - group['ctt']) ** 2).mean())),
                'tb13_mean': float(group['tb13'].mean()),
                'ctt_mean': float(group['ctt'].mean())
            })

    # 保存验证统计
    validation_file = os.path.join(resultPath, 'step4_validation_stats.csv')
    pd.DataFrame(bin_stats).to_csv(validation_file, index=False)
    log(f"  验证统计已保存: {validation_file}")

    # 保存总体报告
    report = {
        'algorithm': 'CTT_LUT_BUILD',
        'datetime': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'input': scan_result,
        'matching': {
            'total_matched_points': initial_count,
            'qc_passed_points': qc_count,
            'qc_rejected_points': initial_count - qc_count,
            'qc_pass_rate': f"{qc_count/initial_count*100:.2f}%"
        },
        'lut': {
            'total_grids': stats['total_grids'],
            'valid_grids': stats['valid_grids'],
            'coverage_rate': f"{stats['coverage_rate']:.2f}%",
            'total_samples': stats['total_samples'],
            'ctt_min': float(stats['ctt_range'][0]),
            'ctt_max': float(stats['ctt_range'][1]),
            'mean_rmse': float(stats['rmse_mean'])
        },
        'validation': {
            'tb13_ctt_bias': validation_stats['tb13_ctt_bias'],
            'tb13_ctt_rmse': validation_stats['tb13_ctt_rmse'],
            'tb13_ctt_corr': validation_stats['tb13_ctt_corr']
        },
        'output_files': {
            'step0_scan_result': scan_file,
            'step1_matched_data': matched_file,
            'step2_qc_data': qc_file,
            'step3_lut_full': result['saved_files']['lut_full'],
            'step3_lut_valid': result['saved_files']['lut_valid'],
            'step4_validation_stats': validation_file
        }
    }

    if result['saved_files']['lut_netcdf']:
        report['output_files']['step3_lut_netcdf'] = result['saved_files']['lut_netcdf']

    report_file = os.path.join(resultPath, 'step4_report.json')
    with open(report_file, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    log(f"  总体报告已保存: {report_file}")

    log("\n" + "=" * 60)
    log("算法执行成功!")
    log("=" * 60)

    return report
