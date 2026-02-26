#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Arspy - 简洁好用的算法框架
"""

# 日志接口
from .logger import init, set_status, add_result, set_metadata, set_coordinates, set_observation_time, add_custom_field, \
    log, fjson, _rjson_helper as rjson

# 文件命名接口
from .naming import parse_name, build_names, build_mapinfo

# 文件保存接口
from .save_file import save_tiff, save_netcdf

class DrawMap:
    def __new__(cls, *args, **kwargs):
        from .qgsmap import DrawMap as _DrawMap
        return _DrawMap(*args, **kwargs)

__version__ = "1.0.0"
