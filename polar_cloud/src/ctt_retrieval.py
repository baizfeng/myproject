#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
  @date    : 2025/01/21
  @file    : ctt_retrieval.py
  @brief   : 云顶温度反演算法 - 基于查找表的薄云订正

  输出值说明 (uint16, 0.1K单位):
  - 有效值: 温度*10 (如 220.5K -> 2205)
  - 65534: 晴空
  - 65535: 无效值
"""

import numpy as np
import pandas as pd


class CTTRetrieval:
    """
    云顶温度反演类

    算法流程:
    1. 厚/薄云分离: 基于分裂窗亮温差 |BT11 - BT12| < delta_thick
    2. 厚云: CTT ≈ BT11 (近似黑体)
    3. 薄云: 使用FY4B查找表订正

    输出格式:
    - uint16, 0.1K单位
    - 有效值: 0-65533 (温度*10)
    - 65534: 晴空
    - 65535: 无效值
    """

    # 厚/薄云分离阈值 (K)
    BTD_THICK_THRESHOLD = 0.2  # |BT11 - BT12| < 0.5K 为厚云
    BT_WARM_THRESHOLD = 260.0  # 排除低层暖云

    # 查找表网格配置
    TB108_BINS = np.arange(180, 341, 2)  # 10.8um亮温: 180-340K, 步长2K
    TB120_BINS = np.arange(180, 341, 2)  # 12.0um亮温: 180-340K, 步长2K
    ZENITH_BINS = np.arange(0, 81, 5)    # 天顶角: 0-80度, 步长5度

    def __init__(self, lut_file):
        """
        初始化反演器,加载查找表

        Parameters
        ----------
        lut_file : str
            查找表文件路径 (CSV格式)
            包含列: tb108, tb120, sat_zenith, clt, ctt, sample_count, ctt_rmse
        """
        self.lut_data = self._load_lut(lut_file)
        # 构建网格查找表
        self._build_grid_lut()

    def _load_lut(self, lut_file):
        """加载查找表"""
        lut = pd.read_csv(lut_file)
        # 过滤样本数>=10的网格
        lut = lut[lut['sample_count'] >= 10].copy()
        print(f"加载查找表: {len(lut)} 个有效网格")
        return lut

    def _build_grid_lut(self):
        """
        构建网格查找表，按云类型组织
        结构: lut_dict[clt_type] = {'tb108': [], 'tb120': [], 'zenith': [], 'ctt': [], 'rmse': []}
        """
        self.lut_dict = {}

        # 获取bin中心值
        tb108_centers = [(self.TB108_BINS[i] + self.TB108_BINS[i+1]) / 2 for i in range(len(self.TB108_BINS)-1)]
        tb120_centers = [(self.TB120_BINS[i] + self.TB120_BINS[i+1]) / 2 for i in range(len(self.TB120_BINS)-1)]
        zenith_centers = [(self.ZENITH_BINS[i] + self.ZENITH_BINS[i+1]) / 2 for i in range(len(self.ZENITH_BINS)-1)]

        # 云类型映射 (简化为3类)
        # 2=Water, 3=Super_Cooled -> 水云 (对应thick cloud)
        # 4=Mixed -> 混合云
        # 5=Ice, 6=Cirrus -> 冰云 (对应thin cloud)
        self.clt_mapping = {
            'water': [2, 3],      # 水云
            'mixed': [4],         # 混合云
            'ice': [5, 6, 7]      # 冰云
        }

        # 为每类云构建查找表
        for cloud_type, clt_codes in self.clt_mapping.items():
            lut_subset = self.lut_data[self.lut_data['clt'].isin(clt_codes)].copy()

            if len(lut_subset) > 0:
                self.lut_dict[cloud_type] = {
                    'tb108': lut_subset['tb108'].values,
                    'tb120': lut_subset['tb120'].values,
                    'zenith': lut_subset['sat_zenith'].values,
                    'ctt': lut_subset['ctt'].values,
                    'rmse': lut_subset['ctt_rmse'].values
                }
                print(f"  {cloud_type}: {len(lut_subset)} 个网格")

        # 默认使用所有数据构建通用查找表（当无法分类时）
        lut_all = self.lut_data.copy()
        self.lut_dict['default'] = {
            'tb108': lut_all['tb108'].values,
            'tb120': lut_all['tb120'].values,
            'zenith': lut_all['sat_zenith'].values,
            'ctt': lut_all['ctt'].values,
            'rmse': lut_all['ctt_rmse'].values
        }
        print(f"  default: {len(lut_all)} 个网格")

    def _classify_cloud_type(self, bt11, bt12, thin_mask):
        """
        对薄云区域进一步分类：水云/混合云/冰云

        分类依据:
        - 水云: BT11 > 273K 且 |BT11-BT12| < 1K
        - 冰云: BT11 < 260K 或 BT11-BT12 > 2K
        - 混合云: 介于两者之间

        Returns
        -------
        cloud_type_map : np.ndarray
            云类型分类结果: 'water', 'mixed', 'ice', 'default'
        """
        cloud_type_map = np.full_like(bt11, 'default', dtype=object)

        if not np.any(thin_mask):
            return cloud_type_map

        # 提取薄云区域
        bt11_thin = bt11[thin_mask]
        bt12_thin = bt12[thin_mask]
        btd_thin = bt11_thin - bt12_thin

        # 分类
        water_idx = (bt11_thin > 273) & (np.abs(btd_thin) < 1)
        ice_idx = (bt11_thin < 260) | (btd_thin > 2)

        # 在薄云掩膜中设置类型
        thin_indices = np.where(thin_mask)
        for idx, is_water, is_ice in zip(zip(*thin_indices), water_idx, ice_idx):
            if is_water:
                cloud_type_map[idx] = 'water'
            elif is_ice:
                cloud_type_map[idx] = 'ice'
            else:
                cloud_type_map[idx] = 'mixed'

        return cloud_type_map

    def _lookup_ctt(self, bt108, bt120, zenith_deg, cloud_type='default'):
        """
        在查找表中查找CTT值

        Parameters
        ----------
        bt108, bt120, zenith_deg : float or np.ndarray
            输入观测值
        cloud_type : str
            云类型 ('water', 'mixed', 'ice', 'default')

        Returns
        -------
        ctt : float or np.ndarray
            查找得到的CTT值
        """
        if cloud_type not in self.lut_dict:
            cloud_type = 'default'

        lut = self.lut_dict[cloud_type]

        # 计算距离权重
        tb108_diff = lut['tb108'] - bt108
        tb120_diff = lut['tb120'] - bt120
        zenith_diff = (lut['zenith'] - zenith_deg) / 10.0  # 天顶角权重降低

        # 使用反距离权重插值
        # 对于标量输入
        if np.isscalar(bt108):
            distances = np.sqrt(tb108_diff**2 + tb120_diff**2 + zenith_diff**2)
            # 找到最近的几个点（k=3）
            k = min(3, len(lut['ctt']))
            nearest_indices = np.argpartition(distances, k)[:k]

            # 反距离权重
            weights = 1.0 / (distances[nearest_indices] + 1e-6)
            weights /= weights.sum()

            ctt = np.sum(lut['ctt'][nearest_indices] * weights)
        else:
            # 对于数组输入
            ctt = np.full_like(bt108, np.nan, dtype=np.float32)
            for i in range(len(bt108)):
                distances = np.sqrt(
                    (lut['tb108'] - bt108[i])**2 +
                    (lut['tb120'] - bt120[i])**2 +
                    ((lut['zenith'] - zenith_deg[i]) / 10.0)**2
                )
                k = min(3, len(lut['ctt']))
                nearest_indices = np.argpartition(distances, k)[:k]
                weights = 1.0 / (distances[nearest_indices] + 1e-6)
                weights /= weights.sum()
                ctt[i] = np.sum(lut['ctt'][nearest_indices] * weights)

        return ctt

    def _classify_cloud(self, bt11, bt12, cloud_mask):
        """
        厚/薄云分类

        Parameters
        ----------
        bt11, bt12 : np.ndarray
            11um和12um亮温 (K)
        cloud_mask : np.ndarray
            云掩膜 (True=云)

        Returns
        -------
        thick_mask, thin_mask : np.ndarray
            厚云和薄云的布尔掩膜
        """
        # 计算分裂窗亮温差
        btd = bt11 - bt12

        # 厚云判据: |BTD| < 阈值
        thick_mask = cloud_mask & (np.abs(btd) < self.BTD_THICK_THRESHOLD)

        # 薄云判据: BTD >= 阈值 且 BT11 < 阈值(排除暖云)
        thin_mask = cloud_mask & (btd >= self.BTD_THICK_THRESHOLD) & (bt11 < self.BT_WARM_THRESHOLD)

        return thick_mask, thin_mask

    def _correct_thin_cloud(self, bt11, bt12, sat_zenith, thin_mask, cloud_type_map=None):
        """
        薄云订正 - 使用查找表

        Parameters
        ----------
        bt11, bt12 : np.ndarray
            11um和12um亮温 (K)
        sat_zenith : np.ndarray
            卫星天顶角 (0.01度单位)
        thin_mask : np.ndarray
            薄云掩膜
        cloud_type_map : np.ndarray
            云类型分类结果

        Returns
        -------
        ctt : np.ndarray
            订正后的云顶温度
        """
        # 初始化输出
        ctt = np.full_like(bt11, np.nan, dtype=np.float32)

        if not np.any(thin_mask):
            return ctt

        # 转换卫星天顶角为度
        zenith_deg = sat_zenith / 100.0

        # 如果没有云类型分类，使用默认
        if cloud_type_map is None:
            cloud_type_map = self._classify_cloud_type(bt11, bt12, thin_mask)

        # 对薄云区域逐个处理
        thin_indices = np.where(thin_mask)
        for idx in zip(*thin_indices):
            i, j = idx
            bt11_val = bt11[i, j]
            bt12_val = bt12[i, j]
            zenith_val = zenith_deg[i, j]

            # 跳过无效值
            if np.isnan(bt11_val) or np.isnan(bt12_val):
                continue

            # 获取云类型
            clt_type = cloud_type_map[i, j]

            # 查找表获取CTT
            ctt_val = self._lookup_ctt(bt11_val, bt12_val, zenith_val, clt_type)

            if not np.isnan(ctt_val):
                ctt[i, j] = ctt_val

        return ctt

    # 输出TIFF填充值定义
    FILLVALUE_CLEAR = 65534  # 晴空填充值
    FILLVALUE_INVALID = 65535  # 无效值填充值

    def retrieve(self, bt11, bt12, cloud_mask, sat_zenith=None):
        """
        执行云顶温度反演

        Parameters
        ----------
        bt11 : np.ndarray
            11um亮温 (K)
        bt12 : np.ndarray
            12um亮温 (K)
        cloud_mask : np.ndarray
            云掩膜 (1=云, 0=晴空, 255=无效值)
        sat_zenith : np.ndarray, optional
            卫星天顶角 (0.01度单位), 如果为None则使用默认值45度

        Returns
        -------
        ctt : np.ndarray
            云顶温度 (uint16, 0.1K单位)
            - 有效值: 温度*10 (如 220.5K -> 2205)
            - 晴空: 65534
            - 无效值: 65535
        thick_mask : np.ndarray
            厚云掩膜
        thin_mask : np.ndarray
            薄云掩膜
        """
        # 初始化输出
        ctt = np.full_like(bt11, np.nan, dtype=np.float32)

        # 判断有效数据区域和晴空区域
        valid_mask = (cloud_mask != 255)  # 非无效值
        clear_mask = (cloud_mask == 0)     # 晴空
        cloud_bool = (cloud_mask == 1)    # 云

        # 如果没有提供卫星天顶角，使用默认值
        if sat_zenith is None:
            sat_zenith = np.full_like(bt11, 4500, dtype=np.float32)  # 45度

        # 厚/薄云分类（仅在云区域进行）
        thick_mask, thin_mask = self._classify_cloud(bt11, bt12, cloud_bool & valid_mask)

        # 厚云: 直接使用BT11
        ctt[thick_mask] = bt11[thick_mask]

        # 薄云: 查找表订正
        cloud_type_map = self._classify_cloud_type(bt11, bt12, thin_mask)
        ctt_thin = self._correct_thin_cloud(bt11, bt12, sat_zenith, thin_mask, cloud_type_map)

        # 对无法通过查找表获取的像素，使用BT11作为后备
        thin_valid = ~np.isnan(ctt_thin)
        ctt[thin_mask & thin_valid] = ctt_thin[thin_mask & thin_valid]

        # 薄云中无法订正的部分使用BT11
        thin_fallback = thin_mask & ~thin_valid
        ctt[thin_fallback] = bt11[thin_fallback]

        # 温度范围检查 (180K - 320K)
        valid_range = (ctt >= 180) & (ctt <= 320)
        ctt[~valid_range] = np.nan

        # 转换为uint16输出格式 (0.1K单位)
        ctt_out = np.full_like(cloud_mask, self.FILLVALUE_INVALID, dtype=np.uint16)

        # 有效云区：温度*10
        cloud_valid = (~np.isnan(ctt)) & cloud_bool & valid_mask
        ctt_out[cloud_valid] = np.clip(ctt[cloud_valid] * 10, 0, 65533).astype(np.uint16)

        # 晴空区域
        ctt_out[clear_mask & valid_mask] = self.FILLVALUE_CLEAR

        return ctt_out, thick_mask, thin_mask
