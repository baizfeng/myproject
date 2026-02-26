#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
  @date    : 2025/01/21
  @file    : cth_retrieval.py
  @brief   : 云顶高度反演 - 基于温压廓线匹配

  输出值说明 (uint16, 0.1hPa单位):
  - 有效值: 气压*10 (如 350.5hPa -> 3505)
  - 65534: 晴空
  - 65535: 无效值
"""

import numpy as np
import xarray as xr
from datetime import datetime
from scipy.interpolate import RegularGridInterpolator


class CTHRetrieval:
    """云顶高度反演类 - 基于温压廓线匹配

    算法流程:
    1. 读取温压廓线数据 (ERA5/T799 pressure levels)
    2. 匹配最临近时刻
    3. 插值到CTT网格（分块优化）
    4. 应用温度拐点掩膜（对流层顶限制）
    5. 匹配气压层（向量化优化 + 动态边界选择）
    """

    CLEAR_SKY = 65534  # 晴空
    FILL_VALUE = 65535  # 填充值

    def __init__(self, tppro_file):
        """初始化，加载温压廓线数据

        参数:
            tppro_file: 温压廓线文件路径 (grib格式)
        """
        self.xds = xr.open_dataset(
            tppro_file,
            engine='cfgrib',
            backend_kwargs={"indexpath": ""}
        )
        self.t = self.xds.t
        self.pressure = self.xds.isobaricInhPa.values

        # 经度转到[-180, 180]
        self.t = self.t.assign_coords(longitude=(self.t.longitude + 180) % 360 - 180)
        self.t = self.t.sortby('longitude')

    def _create_interpolators(self, t_at_time, prof_lat, prof_lon, n_levels):
        """预创建所有气压层的插值器

        参数:
            t_at_time: 指定时刻的温度数据
            prof_lat: 廓线纬度
            prof_lon: 廓线经度
            n_levels: 气压层数量

        返回:
            interpolators: 插值器列表
        """
        interpolators = []
        for k in range(n_levels):
            temp_data = t_at_time.isel(isobaricInhPa=k).values.astype(np.float32)
            interpolator = RegularGridInterpolator(
                (prof_lat, prof_lon),
                temp_data,
                method='linear',
                bounds_error=False,
                fill_value=np.nan
            )
            interpolators.append(interpolator)
        return interpolators

    def _interpolate_to_grid(self, interpolators, lon, lat, height, width, chunk_size=500):
        """分块插值到CTT网格

        参数:
            interpolators: 预创建的插值器列表
            lon, lat: 经纬度数组
            height, width: 图像尺寸
            chunk_size: 分块大小

        返回:
            t_profile: 插值后的温度廓线 [n_levels, height, width]
        """
        n_levels = len(interpolators)
        t_profile = np.full((n_levels, height, width), np.nan, dtype=np.float32)

        # 创建2D网格
        lon_grid, lat_grid = np.meshgrid(lon, lat)

        # 分块处理（避免内存溢出）
        for i_start in range(0, height, chunk_size):
            i_end = min(i_start + chunk_size, height)
            for j_start in range(0, width, chunk_size):
                j_end = min(j_start + chunk_size, width)

                # 该块的经纬度
                lon_chunk = lon_grid[i_start:i_end, j_start:j_end].flatten()
                lat_chunk = lat_grid[i_start:i_end, j_start:j_end].flatten()
                points = np.column_stack([lat_chunk, lon_chunk])

                # 对每个气压层进行插值
                for k in range(n_levels):
                    temp_interp = interpolators[k](points)
                    t_profile[k, i_start:i_end, j_start:j_end] = temp_interp.reshape(
                        i_end - i_start, j_end - j_start
                    )

        return t_profile

    def _apply_inflection_point_mask(self, t_profile):
        """应用温度拐点掩膜（对流层顶限制）

        物理意义:
        - 对流层温度随高度递减，平流层温度随高度递增
        - 对流层顶为温度最小值（拐点）
        - 云顶通常不会高于对流层顶

        参数:
            t_profile: [n_levels, height, width]

        返回:
            t_profile_masked: 应用掩膜后的温度廓线
            inflection_idx: 拐点索引 [height, width]
        """
        # 用 np.inf 填充 nan，以便 argmin 能正确工作
        t_filled = np.where(np.isnan(t_profile), np.inf, t_profile)

        # 找到每个像素的温度最小值索引（拐点）
        inflection_idx = np.argmin(t_filled, axis=0)  # [height, width]

        # 创建掩膜：气压层索引 > 拐点索引的位置设为 True
        n_levels = t_profile.shape[0]
        level_indices = np.arange(n_levels)[:, None, None]  # [n_levels, 1, 1]
        mask = level_indices > inflection_idx[None, :, :]  # [n_levels, height, width]

        # 应用掩膜：高于对流层顶的设为 np.inf
        t_profile_masked = np.where(mask, np.inf, t_profile)

        return t_profile_masked, inflection_idx

    def _match_pressure_with_inflection(self, t_profile, ctt_work, cloud_mask, inflection_idx,
                                        chunk_size=512):
        """分块气压匹配（含拐点逻辑和动态边界选择）

        参数:
            t_profile: 已掩膜的温度廓线 [n_levels, height, width]
            ctt_work: 云顶温度（已过滤） [height, width]
            cloud_mask: 云掩膜 [height, width]
            inflection_idx: 拐点索引 [height, width]
            chunk_size: 分块大小

        返回:
            cth: 云顶气压(hPa) [height, width]
        """
        n_levels = len(self.pressure)
        height, width = ctt_work.shape

        # 初始化输出数组
        cth = np.full((height, width), self.FILL_VALUE, dtype=np.float32)

        # 分块处理
        for i_start in range(0, height, chunk_size):
            i_end = min(i_start + chunk_size, height)
            for j_start in range(0, width, chunk_size):
                j_end = min(j_start + chunk_size, width)

                # 提取当前块的数据
                t_profile_chunk = t_profile[:, i_start:i_end, j_start:j_end]
                ctt_chunk = ctt_work[i_start:i_end, j_start:j_end]
                inflection_chunk = inflection_idx[i_start:i_end, j_start:j_end]
                cloud_chunk = cloud_mask[i_start:i_end, j_start:j_end]

                h_chunk, w_chunk = ctt_chunk.shape

                # 创建有效的ctt掩膜（非nan的像素）
                valid_ctt = ~np.isnan(ctt_chunk)

                # 1. 找到温度最接近的气压层索引（向量化处理小块）
                nearest_idx_chunk = np.zeros((h_chunk, w_chunk), dtype=np.int32)

                # 对每个有效像素找最接近的气压层
                if np.any(valid_ctt):
                    for k in range(n_levels):
                        t_level = t_profile_chunk[k, :, :]
                        diff = np.abs(t_level - ctt_chunk)
                        if k == 0:
                            min_diff = diff.copy()
                            nearest_idx_chunk[:, :] = k
                        else:
                            nearer = diff < min_diff
                            nearest_idx_chunk[nearer] = k
                            min_diff[nearer] = diff[nearer]

                    # 2. 获取最接近层的温度值（向量化）
                    nearest_idx_3d = nearest_idx_chunk[np.newaxis, :, :]
                    t_nearest = np.take_along_axis(t_profile_chunk, nearest_idx_3d, axis=0)[0]

                    # 3. 动态选择边界层
                    tf = (t_nearest > ctt_chunk) & valid_ctt

                    idx_lower = np.where(tf, nearest_idx_chunk, nearest_idx_chunk - 1)
                    idx_upper = np.where(tf, nearest_idx_chunk + 1, nearest_idx_chunk)

                    # 边界限制
                    idx_lower = np.clip(idx_lower, 0, n_levels - 1)
                    idx_upper = np.clip(idx_upper, 0, n_levels - 1)

                    # 4. 批量提取上下层的温度和气压值
                    idx_lower_3d = idx_lower[np.newaxis, :, :]
                    idx_upper_3d = idx_upper[np.newaxis, :, :]

                    t1 = np.take_along_axis(t_profile_chunk, idx_lower_3d, axis=0)[0]
                    t2 = np.take_along_axis(t_profile_chunk, idx_upper_3d, axis=0)[0]

                    p1 = self.pressure[idx_lower]
                    p2 = self.pressure[idx_upper]

                    # 5. 线性插值
                    denom = t2 - t1
                    cth_chunk = np.where(
                        (np.abs(denom) > 0.01) & valid_ctt,
                        p1 + (ctt_chunk - t1) * (p2 - p1) / denom,
                        (p1 + p2) / 2
                    )

                    # 6. 处理边界情况
                    at_boundary = (nearest_idx_chunk == 0) | (nearest_idx_chunk == n_levels - 1)
                    cth_chunk = np.where(at_boundary, self.pressure[nearest_idx_chunk], cth_chunk)

                    # 7. 过滤无效匹配点
                    valid_match = (nearest_idx_chunk != inflection_chunk) & (nearest_idx_chunk != 0)
                    cth_chunk = np.where(valid_match & valid_ctt, cth_chunk, self.FILL_VALUE)
                else:
                    cth_chunk = np.full((h_chunk, w_chunk), self.FILL_VALUE, dtype=np.float32)

                # 8. 应用云掩膜
                cth_chunk = np.where(cloud_chunk, cth_chunk, self.CLEAR_SKY)

                # 将结果写回大数组
                cth[i_start:i_end, j_start:j_end] = cth_chunk

        return cth

    def retrieve(self, ctt, lon, lat, obs_time, cloud_mask):
        """执行云顶高度反演

        参数:
            ctt: 云顶温度(uint16, 0.1K单位), 晴空=65534, 无效=65535
            lon, lat: 经纬度数组(1D)
            obs_time: 观测时间(datetime)
            cloud_mask: 云掩膜 (1=云, 0=晴空, 255=无效值)

        返回:
            cth: 云顶气压(uint16, 0.1hPa单位), 晴空=65534, 无效=65535
        """
        # 1. 匹配时刻
        times = self.t.time.values
        time_diffs = [abs((obs_time - datetime.utcfromtimestamp(t.astype('int64') / 1e9)).total_seconds())
                      for t in times]
        time_idx = np.argmin(time_diffs)

        # 选择指定时刻的数据
        t_at_time = self.t.isel(time=time_idx)

        # 获取廓线网格
        prof_lon = t_at_time.longitude.values
        prof_lat = t_at_time.latitude.values
        n_levels = len(self.pressure)

        # 2. 预创建插值器
        interpolators = self._create_interpolators(t_at_time, prof_lat, prof_lon, n_levels)

        # 3. 分块插值到CTT网格
        height, width = ctt.shape
        t_profile = self._interpolate_to_grid(interpolators, lon, lat, height, width)

        # 4. 应用温度拐点掩膜
        t_profile_masked, inflection_idx = self._apply_inflection_point_mask(t_profile)

        # 5. 准备CTT数据
        ctt_work = ctt.copy().astype(np.float32) / 10.0  # 转换为K
        ctt_work[(ctt_work >= self.CLEAR_SKY * 0.1) | (ctt_work >= self.FILL_VALUE * 0.1)] = np.nan

        # 6. 向量化气压匹配
        cloud_bool = (cloud_mask == 1)
        cth = self._match_pressure_with_inflection(
            t_profile_masked, ctt_work, cloud_bool, inflection_idx
        )

        # 7. 转换为uint16输出格式 (0.1hPa单位)
        cth_out = np.full_like(cloud_mask, self.FILL_VALUE, dtype=np.uint16)

        # 有效云区：气压*10
        valid_cth = (cth != self.FILL_VALUE) & (cth != self.CLEAR_SKY)
        cth_out[valid_cth] = np.clip(cth[valid_cth] * 10, 0, 65533).astype(np.uint16)

        # 晴空区域
        cth_out[cloud_mask == 0] = self.CLEAR_SKY

        return cth_out

    def close(self):
        """关闭数据集"""
        if hasattr(self, 'xds'):
            self.xds.close()
