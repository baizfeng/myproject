#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
算法主文件 - L2云产品处理
"""
import os
import numpy as np
from datetime import datetime
from arspy import (
    log,
    fjson,
    rjson,
    parse_name,
    build_names,
    build_mapinfo,
    save_tiff,
    save_netcdf,
)
from arspy.qgsmap import DrawMap
from .IRSRProcessor import IRSRProcessor
from .cloudmask import CloudDetector
from .ctt_retrieval import CTTRetrieval
from .cth_retrieval import CTHRetrieval


def main(primaryFile, geoFile, clmFile, tpproFile, resultPath, auxPath):
    """主算法函数"""

    # 文件名配置
    input_pattern = r"(?P<sgs>[^_]+)_(?P<satellite>[^_]+)_(?P<sensor>[^_]+)_(?P<yyyymmdd>\d{8})_(?P<HHMMSS>\d{6})_R(?P<resolution>\d+M)_(?P<level>[^.]+)\.(?P<ext>[^.]+)"
    cth_template = "{rootpath}/{satellite}/{sensor}/CLD/{yyyy}/{yyyymmdd}/CTH_P_{sgs}_{satellite}_{sensor}_GBAL_L2_GLL_{yyyymmdd}_{HHMMSS}_{resolution}.{format}"
    ctt_template = "{rootpath}/{satellite}/{sensor}/CLD/{yyyy}/{yyyymmdd}/CTT_P_{sgs}_{satellite}_{sensor}_GBAL_L2_GLL_{yyyymmdd}_{HHMMSS}_{resolution}.{format}"
    clt_template = "{rootpath}/{satellite}/{sensor}/CLD/{yyyy}/{yyyymmdd}/CLT_P_{sgs}_{satellite}_{sensor}_GBAL_L2_GLL_{yyyymmdd}_{HHMMSS}_{resolution}.{format}"
    clm_template = "{rootpath}/{satellite}/{sensor}/CLD/{yyyy}/{yyyymmdd}/CLM_P_{sgs}_{satellite}_{sensor}_GBAL_L2_GLL_{yyyymmdd}_{HHMMSS}_{resolution}.{format}"
    output_formats = ["NC", "TIFF", "PNG"]

    # 解析输入文件名
    params = parse_name(primaryFile, input_pattern)
    log(f"解析参数: {params}")

    # 生成所有格式的输出路径
    yyyy = params.get("yyyymmdd", "")[:4]
    cth_names = build_names(params, cth_template, output_formats, resultPath, yyyy=yyyy)
    ctt_names = build_names(params, ctt_template, output_formats, resultPath, yyyy=yyyy)
    clt_names = build_names(params, clt_template, output_formats, resultPath, yyyy=yyyy)
    clm_names = build_names(params, clm_template, output_formats, resultPath, yyyy=yyyy)

    # 生成绘图mapinfo信息
    cth_mapinfos = build_mapinfo(params, titles="卫星云顶高度产品")
    ctt_mapinfos = build_mapinfo(params, titles="卫星云顶温度产品")
    clt_mapinfos = build_mapinfo(params, titles="卫星云类型产品")
    clm_mapinfos = build_mapinfo(params, titles="卫星云掩膜产品")
    fjson("输出产品文件名预定义")

    proc = IRSRProcessor(primaryFile, geoFile)

    # 定标亮温数据
    bt_data = proc.calibrate([0, 1])  # [2, n_lines, n_pixels]

    # 批量读取辅助地理数据
    geo_vars = ["LandSeaMask", "SensorZenith"]
    geo_data = proc.get_geodata_batch(geo_vars)
    fjson("地理数据读取完成")

    # 合并所有数据后一次性投影: 亮温(2) + 辅助(2) = 4波段
    all_data = np.concatenate(
        [bt_data, np.stack([geo_data[name] for name in geo_vars])], axis=0
    )
    projected, lon, lat = proc.reproject(
        all_data, resolution=0.005, radius_of_influence=5000, fill_value=np.nan
    )
    # 关闭数据集
    proc.close()

    fjson("数据投影完成")

    # ===== 云掩膜产品 =====
    if clmFile == "":
        detector = CloudDetector(
            projected[0, :, :], projected[1, :, :], projected[2, :, :]
        )

        # 执行检测
        cloud_mask = detector.detect(use_texture=False)

        # 保存CLM TIFF
        save_tiff(
            cloud_mask,
            lon,
            lat,
            clm_names["TIFF"],
            resolution=0.005,
            fillvalue=255,
            metadata=[
                {
                    "description": "0:clear,1:cloud,255:fillvalue",
                    "name": "CLM",
                    "scale": "1",
                    "offset": "0",
                    "unit": "",
                    "fillvalue": 255,
                }
            ],
        )
        log(f"CLM TIFF文件已保存: {clm_names['TIFF']}")

    # ===== 云顶温度反演 =====
    lutfile = os.path.join(auxPath, "lut", "FY4B_LUT.csv")
    ctt_retrieval = CTTRetrieval(lutfile)

    ctt, thick_mask, thin_mask = ctt_retrieval.retrieve(
        projected[0, :, :], projected[1, :, :], cloud_mask, projected[3, :, :]
    )

    # 保存CTT TIFF
    save_tiff(
        ctt,
        lon,
        lat,
        ctt_names["TIFF"],
        resolution=0.005,
        fillvalue=65535,
        metadata=[
            {
                "description": "65534:clear,65535:fillvalue",
                "name": "CTT",
                "scale": "0.1",
                "offset": "0",
                "unit": "K",
                "fillvalue": 65535,
            }
        ],
    )
    log(f"CTT TIFF文件已保存: {ctt_names['TIFF']}")

    # 保存CTT NC
    ctt_var_attrs = {
        "CTT": {
            "long_name": "Cloud Top Temperature",
            "units": "K",
            "_FillValue": "65535",
            "valid_min": "0",
            "valid_max": "65533",
            "scale_factor": "0.1",
            "add_offset": "0",
        }
    }
    ctt_global_attrs = {
        "dataset_name": f"{params.get('satellite', '')}_{params.get('sensor', '')}_GBAL_L2_CTT",
        "Title": "Cloud Top Temperature Product",
        "platform_ID": params.get("satellite", ""),
        "instrument_ID": params.get("sensor", ""),
        "processing_level": "L2",
        "date_created": params.get("yyyymmdd", "") + params.get("HHMMSS", ""),
        "spatial_resolution": params.get("resolution", ""),
        "time_coverage_start": params.get("yyyymmdd", "")
        + "T"
        + params.get("HHMMSS", ""),
        "time_coverage_end": params.get("yyyymmdd", "")
        + "T"
        + params.get("HHMMSS", ""),
    }
    save_netcdf(
        {"CTT": ctt},
        lon,
        lat,
        ctt_names["NC"],
        var_attrs=ctt_var_attrs,
        global_attrs=ctt_global_attrs,
    )
    log(f"CTT NetCDF文件已保存: {ctt_names['NC']}")

    # ===== 云类型产品 =====
    clt = np.full_like(cloud_mask, 255, dtype=np.uint8)
    clt[cloud_mask == 0] = 0  # 晴空
    clt[thick_mask] = 1  # 厚云
    clt[thin_mask] = 2  # 薄云

    # 保存CLT TIFF
    save_tiff(
        clt,
        lon,
        lat,
        clt_names["TIFF"],
        resolution=0.005,
        fillvalue=255,
        metadata=[
            {
                "description": "0:clear,1:thick_cloud,2:thin_cloud,255:fillvalue",
                "name": "CLT",
                "scale": "1",
                "offset": "0",
                "unit": "",
                "fillvalue": 255,
            }
        ],
    )
    log(f"CLT TIFF文件已保存: {clt_names['TIFF']}")

    # ===== 云顶高度反演 =====
    if tpproFile != "":
        # 解析观测时间
        hhmmss = params.get("HHMMSS", "000000")
        yyyymmdd = params.get("yyyymmdd", "20250101")
        obs_time = datetime(
            int(yyyymmdd[:4]),
            int(yyyymmdd[4:6]),
            int(yyyymmdd[6:8]),
            int(hhmmss[:2]),
            int(hhmmss[2:4]),
            int(hhmmss[4:6]),
        )

        cth_retrieval = CTHRetrieval(tpproFile)
        cth = cth_retrieval.retrieve(ctt, lon, lat, obs_time, cloud_mask)
        cth_retrieval.close()

        # 保存CTH TIFF
        save_tiff(
            cth,
            lon,
            lat,
            cth_names["TIFF"],
            resolution=0.005,
            fillvalue=65535,
            metadata=[
                {
                    "description": "65534:clear,65535:fillvalue",
                    "name": "CTH",
                    "scale": "0.1",
                    "offset": "0",
                    "unit": "hPa",
                    "fillvalue": 65535,
                }
            ],
        )
        log(f"CTH TIFF文件已保存: {cth_names['TIFF']}")

        # 保存CTH NC
        cth_var_attrs = {
            "CTH": {
                "long_name": "Cloud Top Height",
                "units": "hPa",
                "_FillValue": "65535",
                "valid_min": "0",
                "valid_max": "1200",
                "scale_factor": "0.1",
                "add_offset": "0",
            }
        }
        cth_global_attrs = {
            "dataset_name": f"{params.get('satellite', '')}_{params.get('sensor', '')}_GBAL_L2_CTH",
            "Title": "Cloud Top Height Product",
            "platform_ID": params.get("satellite", ""),
            "instrument_ID": params.get("sensor", ""),
            "processing_level": "L2",
            "date_created": params.get("yyyymmdd", "") + params.get("HHMMSS", ""),
            "spatial_resolution": params.get("resolution", ""),
            "time_coverage_start": params.get("yyyymmdd", "")
            + "T"
            + params.get("HHMMSS", ""),
            "time_coverage_end": params.get("yyyymmdd", "")
            + "T"
            + params.get("HHMMSS", ""),
        }
        save_netcdf(
            {"CTH": cth},
            lon,
            lat,
            cth_names["NC"],
            var_attrs=cth_var_attrs,
            global_attrs=cth_global_attrs,
        )
        log(f"CTH NetCDF文件已保存: {cth_names['NC']}")

    # ===== 专题图输出 =====
    template = os.path.join(auxPath, "glob", "template.qgs")

    clm_qml = os.path.join(auxPath, "style", "CLM.qml")
    clt_qml = os.path.join(auxPath, "style", "CLT.qml")
    ctt_qml = os.path.join(auxPath, "style", "CTT.qml")
    cth_qml = os.path.join(auxPath, "style", "CTH.qml")

    draw = DrawMap()

    # CLM专题图
    draw.draw_single_map(
        clm_names["TIFF"], clm_names["PNG"], template, clm_qml, clm_mapinfos
    )
    log(f"CLM专题图输出完成: {clm_names['PNG']}")

    # CLT专题图
    draw.draw_single_map(
        clt_names["TIFF"], clt_names["PNG"], template, clt_qml, clt_mapinfos
    )
    log(f"CLT专题图输出完成: {clt_names['PNG']}")

    # CTT专题图
    draw.draw_single_map(
        ctt_names["TIFF"], ctt_names["PNG"], template, ctt_qml, ctt_mapinfos
    )
    log(f"CTT专题图输出完成: {ctt_names['PNG']}")

    # CTH专题图
    if tpproFile != "":
        draw.draw_single_map(
            cth_names["TIFF"], cth_names["PNG"], template, cth_qml, cth_mapinfos
        )
        log(f"CTH专题图输出完成: {cth_names['PNG']}")

    # 保存结果信息到resultjson
    all_names = {
        "CTT": ctt_names,
        "CTH": cth_names if tpproFile != "" else None,
    }
    rjson.info(all_names, result_path=resultPath, product_level="L2")
