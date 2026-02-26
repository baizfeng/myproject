#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
算法配置文件
"""

# ==================== 算法信息 ====================
algorithm_name = "POLAR_CLOUD"
algorithm_description = "云顶温度和云顶高度产品反演算法"
key_steps = ["文件名定义", "数据读取", "数据处理", "数据输出"]

# ==================== 输入字段定义 ====================
INPUT = [
    "primaryFile",
    "geoFile",
    "clmFile",
    "tpproFile",
    "resultPath",
    "auxPath"
]
