#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
算法配置文件
"""

# ==================== 算法信息 ====================
algorithm_name = "POLAR_L1"
algorithm_description = "L1数据辐射定标算法"
key_steps = ["文件名定义", "数据读取", "数据处理", "数据输出"]

# ==================== 输入字段定义 ====================
INPUT = [
    "primaryFile",
    "geoFile",
    "resultPath",
    "auxPath"
]
