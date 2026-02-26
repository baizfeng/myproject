#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
  @date    : 2025/12/24
  @author  : baizhaofeng
  @email   : zfengbai@gmail.com
  @file    : IRSRProcessor.py
"""

"""
IRSR L1 数据处理类
功能: 辐射定标 → 地理投影 → 保存为多波段 GeoTIFF
"""
import os
import glob
import numpy as np
import xarray as xr
from pyresample import geometry, kd_tree
from osgeo import gdal


class IRSRProcessor:
    """IRSR L1 数据处理器"""

    # Planck 常数
    C1 = 1.191042e-5  # mW/(m²·sr·cm⁻⁴)
    C2 = 1.4387752  # cm·K

    def __init__(self, l1_file, geo_file):
        self.ds_l1 = xr.open_dataset(l1_file, engine="h5netcdf")
        self.ds_geo = xr.open_dataset(geo_file, engine="h5netcdf")

        # 核心数据
        self.earth_view = self.ds_l1['Earth_View'].values  # [band, line, pixel]

        # 定标系数 [2, n_frames, 24]
        # 第一维: [0]=波段0, [1]=波段1
        # 第三维: [0]=斜率, [1]=截距
        self.calib_coef = self.ds_l1['Emissive_Calibration_Coefficients'].values

        # 中心波数 (每个波段有12个探测器的波数，取平均)
        center_wn_all = np.array(self.ds_l1.attrs['Emissive_Center_Wave_Number'])
        # 前12个对应波段0 (10.8μm, ~926 cm⁻¹)
        # 接下来12个对应波段1 (12.0μm, ~833 cm⁻¹)
        self.center_wn = np.array([
            np.mean(center_wn_all[0:12]),  # 波段0平均波数
            np.mean(center_wn_all[12:24])  # 波段1平均波数
        ])

        # 扫描帧数
        self.n_frames = self.ds_l1.attrs['Number Of Scans']  # 623

        # 填充值
        self.fill_value = self.ds_l1['Earth_View'].attrs.get('fillValue', 65535)

        # 地理信息
        self.lon = self.ds_geo['Longitude'].values
        self.lat = self.ds_geo['Latitude'].values

    def get_geodata(self, var_name):
        """
        从GEO文件读取指定变量

        参数:
            var_name: str - 变量名，如 'SolarZenith', 'LandSeaMask' 等

        返回:
            data: np.ndarray - 变量数据
        """
        if var_name in self.ds_geo:
            return self.ds_geo[var_name].values
        else:
            raise ValueError(f"GEO文件中未找到变量: {var_name}")

    def get_geodata_batch(self, var_names):
        """批量读取GEO文件变量

        参数:
            var_names: 变量名列表

        返回:
            dict: {变量名: 数据数组}
        """
        return {name: self.get_geodata(name) for name in var_names}

    def _radiance_to_bt(self, radiance, wave_number):
        """
        使用Planck逆函数将辐射亮度转换为亮度温度

        参数:
            radiance: 辐射亮度 (mW/(m²·sr·cm⁻¹))
            wave_number: 中心波数 (cm⁻¹)

        返回:
            亮度温度 (K)
        """
        # 避免除零和对数错误
        radiance = np.maximum(radiance, 1e-10)

        v3 = wave_number ** 3
        ratio = self.C1 * v3 / radiance
        ratio = np.maximum(ratio, 1e-10)

        bt = self.C2 * wave_number / np.log(1.0 + ratio)

        return bt

    def calibrate(self, band_indices=[0, 1]):
        """
        定标多个热红外通道，返回三维亮温数组 [n_bands, n_lines, n_pixels]

        参数:
            band_indices: 通道索引列表，例如 [0, 1] 或 [0]
                         只支持前两个热红外波段 (索引 0 和 1)

        返回:
            np.ndarray: 形状为 (len(band_indices), n_lines, n_pixels) 的亮温数据
        """
        if isinstance(band_indices, int):
            band_indices = [band_indices]

        # 检查波段索引
        for ch in band_indices:
            if ch not in [0, 1]:
                raise ValueError(f"波段索引 {ch} 无效，只支持热红外波段 0 和 1")

        results = []
        for ch in band_indices:
            print(f"  定标通道 {ch + 1}...")
            bt = self._calibrate_single(ch)
            results.append(bt)

        return np.stack(results, axis=0)  # [n_bands, n_lines, n_pixels]

    def _calibrate_single(self, band_idx):
        """
        定标单个热红外通道

        定标流程:
        1. 使用预计算的定标系数: 辐射亮度 = 斜率 × DN + 截距
        2. 每12行使用同一组定标系数
        3. 使用Planck逆函数转换为亮度温度

        参数:
            band_idx: 波段索引 (0 或 1)

        返回:
            亮温数组 [n_lines, n_pixels]
        """
        # 获取该波段的中心波数
        wave_number = self.center_wn[band_idx]

        # 获取DN值 [n_lines, n_pixels]
        dn_earth = self.earth_view[band_idx]
        n_lines, n_pixels = dn_earth.shape

        # 获取定标系数
        # calib_coef[band_idx, :, 0] = 斜率
        # calib_coef[band_idx, :, 1] = 截距
        slope = self.calib_coef[band_idx, :, 0]  # [n_frames]
        intercept = self.calib_coef[band_idx, :, 1]  # [n_frames]

        # 初始化输出数组
        radiance = np.full((n_lines, n_pixels), np.nan, dtype=np.float32)

        # 逐行定标
        for line in range(n_lines):
            # 计算帧索引 (每12行使用同一个系数)
            frame_idx = line // 12
            if frame_idx >= self.n_frames:
                frame_idx = self.n_frames - 1

            # 获取当前行的DN值
            dn_line = dn_earth[line, :]

            # 创建有效数据掩码
            valid_mask = (dn_line != self.fill_value) & (dn_line > 0)

            if np.any(valid_mask):
                # 计算辐射亮度: L = slope * DN + intercept
                radiance[line, valid_mask] = (
                        slope[frame_idx] * dn_line[valid_mask] +
                        intercept[frame_idx]
                )

        # 将辐射亮度转换为亮度温度
        bt = self._radiance_to_bt(radiance, wave_number)

        # 将无效值设为 NaN
        bt[~np.isfinite(radiance)] = np.nan

        return bt

    def reproject(self, data, resolution=0.005, radius_of_influence=5000, fill_value=np.nan):
        """
        重投影支持三维输入 [n_bands, n_lines, n_pixels]
        返回投影后的数据和坐标信息

        参数:
            data: 可以是 2D (单波段) 或 3D (多波段) numpy 数组
            resolution: 目标分辨率 (度)
            radius_of_influence: 影响半径 (米)
            fill_value: 填充值

        返回:
            data: np.ndarray [n_bands, height, width]
            lon: np.ndarray [width] - 经度坐标
            lat: np.ndarray [height] - 纬度坐标
        """
        if data.ndim == 2:
            data = data[np.newaxis, ...]  # 转换为 [1, n_lines, n_pixels]

        n_bands, n_lines, n_pixels = data.shape

        # 准备源几何
        valid_mask = (
                np.isfinite(self.lon) & np.isfinite(self.lat) &
                (self.lon >= -180) & (self.lon <= 180) &
                (self.lat >= -90) & (self.lat <= 90)
        )

        src = geometry.SwathDefinition(lons=self.lon, lats=self.lat)

        # 确定目标网格（只使用有效值）
        valid_lon = self.lon[valid_mask]
        valid_lat = self.lat[valid_mask]

        if len(valid_lon) == 0 or len(valid_lat) == 0:
            raise ValueError("没有有效的经纬度数据")

        lon_min, lon_max = valid_lon.min(), valid_lon.max()
        lat_min, lat_max = valid_lat.min(), valid_lat.max()
        x = np.arange(lon_min, lon_max + resolution / 2, resolution)
        y = np.arange(lat_max, lat_min - resolution / 2, -resolution)
        x2d, y2d = np.meshgrid(x, y)

        dst = geometry.SwathDefinition(lons=x2d, lats=y2d)

        # 对每个波段分别重采样
        projected_bands = []
        for b in range(n_bands):
            print(f"  投影波段 {b + 1}/{n_bands}...")
            band_data = data[b]
            band_clean = np.where(valid_mask, band_data, fill_value)
            resampled = kd_tree.resample_nearest(
                src, band_clean, dst,
                radius_of_influence=radius_of_influence,
                fill_value=fill_value
            )
            projected_bands.append(resampled)

        # 堆叠为 [band, y, x]
        projected = np.stack(projected_bands, axis=0)

        return projected, x, y

    def close(self):
        self.ds_l1.close()
        self.ds_geo.close()
