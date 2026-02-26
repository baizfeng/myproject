#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
算法主文件 - L1数据处理
"""
import os
import numpy as np
from arspy import log, fjson, rjson, parse_name, build_names, build_mapinfo, save_tiff, save_netcdf, DrawMap
from .IRSRProcessor import IRSRProcessor


def main(primaryFile, geoFile, resultPath, auxPath):
    """主算法函数"""

    # 文件名配置
    input_pattern = r"(?P<site>[^_]+)_(?P<satellite>[^_]+)_(?P<sensor>[^_]+)_(?P<yyyymmdd>\d{8})_(?P<HHMMSS>\d{6})_R(?P<resolution>\d+M)_(?P<level>[^.]+)\.(?P<ext>[^.]+)"
    output_template = "{rootpath}/{satellite}/{sensor}/{level}/{yyyy}/{yyyymmdd}/{satellite}_{sensor}_GBAL_{level}_{resolution}_GLL_{yyyymmdd}_{HHMMSS}.{format}"
    output_formats = ["NC", "TIFF:IR11/IR12", "PNG"]

    # 解析输入文件名
    params = parse_name(primaryFile, input_pattern)
    log(f"解析参数: {params}")

    # 生成所有格式的输出路径
    yyyy = params.get("yyyymmdd", "")[:4]
    names = build_names(params, output_template, output_formats, resultPath, yyyy=yyyy)

    # 生成绘图mapinfo信息
    mapinfos = build_mapinfo(params, bands=['IR11', 'IR12'],
                             titles=['卫星长波红外通道亮温(IR:10.8μm)', '卫星长波红外通道亮温(IR:12.0μm)'])

    fjson("输出产品文件名预定义")

    proc = IRSRProcessor(primaryFile, geoFile)

    # 定标亮温数据
    bt_data = proc.calibrate([0, 1])  # [2, n_lines, n_pixels]

    # 批量读取辅助地理数据
    geo_vars = ['LandSeaMask', 'LandCover', 'SensorZenith', 'SensorAzimuth', 'SolarAzimuth', 'SolarZenith']
    geo_data = proc.get_geodata_batch(geo_vars)
    fjson("地理数据读取完成")

    # 合并所有数据后一次性投影: 亮温(2) + 辅助(6) = 8波段
    # 使用NaN作为填充值，避免缩放后溢出，且不与有效数据冲突
    all_data = np.concatenate([bt_data, np.stack([geo_data[name] for name in geo_vars])], axis=0)
    projected, lon, lat = proc.reproject(all_data, resolution=0.005, radius_of_influence=5000, fill_value=np.nan)
    # 关闭数据集
    proc.close()

    fjson("数据投影完成")

    # 数据缩放处理（减小存储空间）
    # IR: 亮温缩放100倍存储为uint16
    ir_scaled = (projected[:2] * 100).astype(np.uint16)
    ir_scaled[np.isnan(projected[:2])] = 65535  # 恢复填充值
    # 角度数据: 缩放100倍存储为uint16
    sensor_zenith = (projected[4] * 100).astype(np.uint16)
    sensor_zenith[np.isnan(projected[4])] = 65535
    sensor_azimuth = (projected[5] * 100).astype(np.uint16)
    sensor_azimuth[np.isnan(projected[5])] = 65535
    solar_azimuth = (projected[6] * 100).astype(np.uint16)
    solar_azimuth[np.isnan(projected[6])] = 65535
    solar_zenith = (projected[7] * 100).astype(np.uint16)
    solar_zenith[np.isnan(projected[7])] = 65535
    # 分类数据: 直接使用uint8
    landsea_mask = projected[2].astype(np.uint8)
    landsea_mask[np.isnan(projected[2])] = 255
    land_cover = projected[3].astype(np.uint8)
    land_cover[np.isnan(projected[3])] = 255

    # TIFF波段元数据（含缩放因子和偏移）
    tiff_metadata = [
        {'description': 'BT 10.8μm', 'wavelength': '10.8', 'name': 'IR11', 'scale': '0.01', 'offset': '0', 'unit': 'K',
         'fillvalue': 65535},
        {'description': 'BT 12.0μm', 'wavelength': '12.0', 'name': 'IR12', 'scale': '0.01', 'offset': '0', 'unit': 'K',
         'fillvalue': 65535},
        {'description': 'LandSeaMask', 'name': 'LandSeaMask', 'scale': '1.0', 'offset': '0', 'unit': '1',
         'fillvalue': 255},
        {'description': 'LandCover', 'name': 'LandCover', 'scale': '1.0', 'offset': '0', 'unit': '1', 'fillvalue': 255},
        {'description': 'SensorZenith', 'name': 'SensorZenith', 'scale': '0.01', 'offset': '0', 'unit': 'degrees',
         'fillvalue': 65535},
        {'description': 'SensorAzimuth', 'name': 'SensorAzimuth', 'scale': '0.01', 'offset': '0', 'unit': 'degrees',
         'fillvalue': 65535},
        {'description': 'SolarAzimuth', 'name': 'SolarAzimuth', 'scale': '0.01', 'offset': '0', 'unit': 'degrees',
         'fillvalue': 65535},
        {'description': 'SolarZenith', 'name': 'SolarZenith', 'scale': '0.01', 'offset': '0', 'unit': 'degrees',
         'fillvalue': 65535}
    ]

    # 组装TIFF数据
    tiff_data = np.stack([ir_scaled[0], ir_scaled[1], landsea_mask, land_cover,
                          sensor_zenith, sensor_azimuth, solar_azimuth, solar_zenith])

    # 保存TIFF
    save_tiff(tiff_data, lon, lat, names["TIFF"], resolution=0.005, metadata=tiff_metadata)
    log(f"TIFF文件已保存: {names["TIFF"]}")

    # 准备NC数据字典（IR为3D，其他为2D）
    nc_data_dict = {
        'IR': ir_scaled,
        'LandSeaMask': landsea_mask,
        'LandCover': land_cover,
        'SensorZenith': sensor_zenith,
        'SensorAzimuth': sensor_azimuth,
        'SolarAzimuth': solar_azimuth,
        'SolarZenith': solar_zenith
    }

    # NC变量属性（包含填充值、有效值范围、缩放因子和偏移）
    nc_var_attrs = {
        'IR': {
            'long_name': 'Brightness Temperature',
            'units': 'K',
            '_FillValue': '65535',
            'valid_min': '0',
            'valid_max': '40000',
            'scale_factor': '0.01',
            'add_offset': '0'
        },
        'LandSeaMask': {
            'long_name': 'LandSeaMask',
            'units': '1',
            '_FillValue': '255',
            'valid_min': '0',
            'valid_max': '254',
            'scale_factor': '1.0',
            'add_offset': '0'
        },
        'LandCover': {
            'long_name': 'LandCover',
            'units': '1',
            '_FillValue': '255',
            'valid_min': '0',
            'valid_max': '254',
            'scale_factor': '1.0',
            'add_offset': '0'
        },
        'SensorZenith': {
            'long_name': 'SensorZenith',
            'units': 'degrees',
            '_FillValue': '65535',
            'valid_min': '0',
            'valid_max': '9000',
            'scale_factor': '0.01',
            'add_offset': '0'
        },
        'SensorAzimuth': {
            'long_name': 'SensorAzimuth',
            'units': 'degrees',
            '_FillValue': '65535',
            'valid_min': '0',
            'valid_max': '36000',
            'scale_factor': '0.01',
            'add_offset': '0'
        },
        'SolarAzimuth': {
            'long_name': 'SolarAzimuth',
            'units': 'degrees',
            '_FillValue': '65535',
            'valid_min': '0',
            'valid_max': '36000',
            'scale_factor': '0.01',
            'add_offset': '0'
        },
        'SolarZenith': {
            'long_name': 'SolarZenith',
            'units': 'degrees',
            '_FillValue': '65535',
            'valid_min': '0',
            'valid_max': '18000',
            'scale_factor': '0.01',
            'add_offset': '0'
        }
    }

    # NC全局属性
    nc_global_attrs = {
        'dataset_name': f"{params.get('satellite', '')}_{params.get('sensor', '')}_GBAL_L1",
        'Project': 'Arspy_ai',
        'Title': 'Global L1 Data Product',
        'platform_ID': params.get('satellite', ''),
        'instrument_ID': params.get('sensor', ''),
        'processing_level': 'L1',
        'date_created': params.get('yyyymmdd', '') + params.get('HHMMSS', ''),
        'spatial_resolution': params.get('resolution', ''),
        'time_coverage_start': params.get('yyyymmdd', '') + 'T' + params.get('HHMMSS', ''),
        'time_coverage_end': params.get('yyyymmdd', '') + 'T' + params.get('HHMMSS', ''),
        'Version_Of_Software': '1.0'
    }

    # 保存NC
    save_netcdf(nc_data_dict, lon, lat, names["NC"], var_attrs=nc_var_attrs, global_attrs=nc_global_attrs)
    log(f"NetCDF文件已保存: {names["NC"]}")

    template = os.path.join(auxPath, "glob", "template.qgs")
    ir11qml = os.path.join(auxPath, "style", "IR11.qml")
    ir12qml = os.path.join(auxPath, "style", "IR12.qml")

    draw = DrawMap()
    draw.draw_single_map(names["TIFF"], names["PNG.IR11"], template, ir11qml, mapinfos["IR11"])
    log("IR11产品专题图输出完成:" + names["PNG.IR11"])

    draw.draw_single_map(names["TIFF"], names["PNG.IR12"], template, ir12qml, mapinfos["IR12"])
    log("IR12产品专题图输出完成:" + names["PNG.IR12"])

    # 保存结果信息到resultjson
    rjson.info(names, result_path=resultPath, product_level="L1")
