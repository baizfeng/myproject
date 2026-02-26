#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
  @date    : 2024/10/4 14:30
  @author  : baizhaofeng
  @email   : zfengbai@gmail.com
  @file    : cloud_mask.py
  云判识算法：基于10.8um和12um红外通道亮温数据
"""

"""
气象遥感云判识算法
基于FY-4A/AGRI类似的红外双通道云检测方法
参考: 气象卫星云检测技术规范

物理原理:
1. 云顶温度通常低于地表温度
2. 亮温差 BTD(11-12) 可以区分不同云类型
3. 高云（卷云）: BT低, BTD > 0
4. 中低云: BT中等, BTD ≈ 0
5. 海陆表面温度特征不同，需要分别处理

输出值说明:
- 1: 云
- 0: 晴空
- 255: 无效值（超出有效范围的数据）
"""

import rasterio
import numpy as np
from scipy import ndimage
from typing import Tuple, Dict


class CloudDetector:
    """
    云检测器 - 使用自适应多通道阈值方法
    """

    def __init__(self, bt11_data: np.ndarray, bt12_data: np.ndarray,
                 land_sea_mask: np.ndarray):
        """
        初始化云检测器

        参数:
            bt11_data: 10.8μm 亮温数据 (K)
            bt12_data: 12μm 亮温数据 (K)
            land_sea_mask: 海陆掩膜 (1=陆地, 0=海洋)
        """
        self.bt11 = bt11_data
        self.bt12 = bt12_data
        self.mask = land_sea_mask

        # 有效数据范围
        self.valid_min = 200  # K
        self.valid_max = 350  # K

        # 创建有效数据掩膜
        self.valid_mask = (
            (self.bt11 >= self.valid_min) & (self.bt11 <= self.valid_max) &
            (self.bt12 >= self.valid_min) & (self.bt12 <= self.valid_max) &
            (self.mask <= 1)  # 排除掩膜中的无效值
        )

        # 计算亮温差
        self.btd = self.bt11 - self.bt12

        # 分离陆地和海洋
        self.land_mask = (self.mask == 1) & self.valid_mask
        self.ocean_mask = (self.mask == 0) & self.valid_mask

    def _calculate_adaptive_thresholds(self) -> Dict[str, Dict]:
        """
        基于数据统计特征计算自适应阈值

        返回:
            包含陆地和海洋阈值的字典
        """
        thresholds = {
            'land': {},
            'ocean': {}
        }

        # 陆地阈值
        if np.sum(self.land_mask) > 1000:  # 需要足够的陆地像素
            bt11_land = self.bt11[self.land_mask]
            btd_land = self.btd[self.land_mask]

            # 使用百分位数确定阈值（更鲁棒）
            # 云顶温度通常低于地表
            thresholds['land']['bt11_threshold'] = np.percentile(bt11_land, 15) - 5
            thresholds['land']['bt11_strict'] = np.percentile(bt11_land, 5)

            # BTD阈值（正值可能指示高云）
            thresholds['land']['btd_high_cloud'] = 2.0  # K
            thresholds['land']['btd_low_cloud'] = -1.0  # K

            # 温度均匀性检验（云通常较均匀）
            thresholds['land']['std_threshold'] = 3.0  # K
        else:
            # 默认阈值（当数据不足时）
            thresholds['land']['bt11_threshold'] = 270  # K
            thresholds['land']['bt11_strict'] = 260  # K
            thresholds['land']['btd_high_cloud'] = 2.0  # K
            thresholds['land']['btd_low_cloud'] = -1.0  # K
            thresholds['land']['std_threshold'] = 3.0  # K

        # 海洋阈值
        if np.sum(self.ocean_mask) > 1000:
            bt11_ocean = self.bt11[self.ocean_mask]
            btd_ocean = self.btd[self.ocean_mask]

            # 海洋表面温度通常较均匀
            thresholds['ocean']['bt11_threshold'] = np.percentile(bt11_ocean, 20) - 8
            thresholds['ocean']['bt11_strict'] = np.percentile(bt11_ocean, 5) - 3

            thresholds['ocean']['btd_high_cloud'] = 1.5  # K
            thresholds['ocean']['btd_low_cloud'] = -0.5  # K
            thresholds['ocean']['std_threshold'] = 2.0  # K
        else:
            # 默认阈值
            thresholds['ocean']['bt11_threshold'] = 275  # K
            thresholds['ocean']['bt11_strict'] = 265  # K
            thresholds['ocean']['btd_high_cloud'] = 1.5  # K
            thresholds['ocean']['btd_low_cloud'] = -0.5  # K
            thresholds['ocean']['std_threshold'] = 2.0  # K

        return thresholds

    def _detect_by_threshold(self, surface_type: str,
                            thresholds: Dict) -> np.ndarray:
        """
        基于阈值检测云

        参数:
            surface_type: 'land' 或 'ocean'
            thresholds: 阈值字典

        返回:
            云掩膜 (1=云, 0=晴空)
        """
        if surface_type == 'land':
            mask = self.land_mask
        else:
            mask = self.ocean_mask

        if np.sum(mask) == 0:
            return np.zeros_like(self.bt11, dtype=np.uint8)

        # 提取区域数据
        bt11_region = self.bt11[mask]
        btd_region = self.btd[mask]

        # 初始化晴空掩膜 (0=晴空)
        cloud = np.zeros_like(bt11_region, dtype=np.uint8)

        # 测试1: 低温检测（所有云类型）
        bt11_th = thresholds[surface_type]['bt11_threshold']
        bt11_strict = thresholds[surface_type]['bt11_strict']
        cloud |= (bt11_region < bt11_th).astype(np.uint8)

        # 测试2: 高云检测（低温 + 正BTD）
        btd_high = thresholds[surface_type]['btd_high_cloud']
        high_cloud = (bt11_region < bt11_strict) & (btd_region > btd_high)
        cloud |= high_cloud.astype(np.uint8)

        # 测试3: 低云检测（中等温度 + 负BTD）
        btd_low = thresholds[surface_type]['btd_low_cloud']
        low_cloud = (bt11_region < bt11_th + 10) & (bt11_region > bt11_strict) & \
                    (btd_region < btd_low)
        cloud |= low_cloud.astype(np.uint8)

        # 创建完整掩膜
        cloud_full = np.zeros_like(self.bt11, dtype=np.uint8)
        cloud_full[mask] = cloud

        return cloud_full

    def _detect_by_texture(self, surface_type: str,
                          thresholds: Dict) -> np.ndarray:
        """
        基于纹理特征检测云（云通常比地表更均匀）
        """
        if surface_type == 'land':
            mask = self.land_mask
        else:
            mask = self.ocean_mask

        if np.sum(mask) == 0:
            return np.zeros_like(self.bt11, dtype=np.uint8)

        # 计算局部标准差（使用小窗口减少计算量）
        kernel_size = 5
        bt11_valid = np.where(self.valid_mask, self.bt11, np.nan)
        local_std = ndimage.generic_filter(
            bt11_valid,
            lambda x: np.nanstd(x),
            size=kernel_size,
            mode='constant',
            cval=np.nan
        )

        # 低标准差可能是云
        std_th = thresholds[surface_type]['std_threshold']
        texture_cloud = (local_std < std_th) & mask

        return texture_cloud.astype(np.uint8)

    def detect(self, use_texture: bool = True) -> np.ndarray:
        """
        执行云检测

        参数:
            use_texture: 是否使用纹理特征

        返回:
            cloud_mask: 云掩膜 (1=云, 0=晴空, 255=无效值)
        """
        # 计算自适应阈值
        thresholds = self._calculate_adaptive_thresholds()

        # 阈值法检测
        cloud_land = self._detect_by_threshold('land', thresholds)
        cloud_ocean = self._detect_by_threshold('ocean', thresholds)

        # 合并 (1=云, 0=晴空)
        cloud_mask = cloud_land | cloud_ocean

        # 纹理法检测（可选）
        if use_texture:
            texture_land = self._detect_by_texture('land', thresholds)
            texture_ocean = self._detect_by_texture('ocean', thresholds)
            texture_cloud = texture_land | texture_ocean

            # 纹理法主要用于辅助检测（补充可能遗漏的云）
            cloud_mask |= texture_cloud

        # 将无效数据区域设置为255
        cloud_mask = np.where(self.valid_mask, cloud_mask, 255).astype(np.uint8)

        return cloud_mask
