#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
葵花卫星HSD数据读取模块
参考: /mnt/e/hxcode/polar_satellite/himawari9_hsd2tif.py
"""
import os
import numpy as np
import glob
import bz2
import tempfile
from contextlib import closing
from datetime import datetime
from osgeo import gdal, osr


# HSD文件格式定义
def get_formation(res):
    """根据分辨率获取HSD文件格式"""
    return [
        ('bn', 'i1', 1), ('bl', 'i2', 1), ('thb', 'i2', 1), ('bo', 'i1', 1),
        ('sn', 'S1', 16), ('pcn', 'S1', 16), ('oa', 'S1', 4), ('obf', 'S1', 2),
        ('ot', 'i2', 1), ('ost', 'float64', 1), ('oet', 'float64', 1),
        ('fct', 'float64', 1), ('thl', 'i4', 1), ('tdl', 'i4', 1),
        ('qf1', 'i1', 1), ('qf2', 'i1', 1), ('qf3', 'i1', 1), ('qf4', 'i1', 1),
        ('ffv', 'S1', 32), ('fn', 'S1', 128), ('null1', 'S1', 40),
        ('bn2', 'i1', 1), ('bl2', 'i2', 1), ('nbpp', 'i2', 1), ('noc', 'i2', 1),
        ('nol', 'i2', 1), ('cffdb', 'i1', 1), ('null2', 'S1', 40),
        ('bn3', 'i1', 1), ('bl3', 'i2', 1), ('sl', 'float64', 1),
        ('CFAC', 'i4', 1), ('LFAC', 'i4', 1), ('COFF', 'float32', 1),
        ('LOFF', 'float32', 1), ('dfectvs', 'float64', 1), ('eer', 'float64', 1),
        ('epr', 'float64', 1), ('var1', 'float64', 1), ('var2', 'float64', 1),
        ('var3', 'float64', 1), ('cfsd', 'float64', 1), ('rt', 'i2', 1),
        ('rs', 'i2', 1), ('null3', 'S1', 40),
        ('bn4', 'i1', 1), ('bl4', 'i2', 1), ('ni', 'float64', 1),
        ('ssplon', 'float64', 1), ('ssplat', 'float64', 1), ('dfects4', 'float64', 1),
        ('nlat', 'float64', 1), ('nlon', 'float64', 1), ('sp', 'float64', 3),
        ('mp', 'float64', 3), ('null4', 'S1', 40),
        ('bn5', 'i1', 1), ('bl5', 'i2', 1), ('bdn', 'i2', 1), ('cwl', 'float64', 1),
        ('vnobpp', 'i2', 1), ('cvoep', 'uint16', 1), ('cvoposa', 'uint16', 1),
        ('gfcce', 'float64', 1), ('cfcce', 'float64', 1), ('c0', 'float64', 1),
        ('c1', 'float64', 1), ('c2', 'float64', 1), ('C0', 'float64', 1),
        ('C1', 'float64', 1), ('C2', 'float64', 1), ('sol', 'float64', 1),
        ('pc', 'float64', 1), ('bc', 'float64', 1), ('null5', 'S1', 40),
        ('b06n01', 'i1', 1), ('b06n02', 'i2', 1), ('b06n03', 'float64', 1),
        ('b06n04', 'float64', 1), ('b06n05', 'float64', 1), ('b06n06', 'float64', 1),
        ('b06n07', 'float64', 1), ('b06n08', 'float64', 1), ('b06n09', 'float64', 1),
        ('b06n10', 'float64', 1), ('b06n11', 'float32', 1), ('b06n12', 'float32', 1),
        ('b06n13', 'S1', 128), ('b06n14', 'S1', 56),
        ('b07n01', 'i1', 1), ('b07n02', 'i2', 1), ('b07n03', 'i1', 1),
        ('b07n04', 'i1', 1), ('b07n05', 'i2', 1), ('b07n06', 'S1', 40),
        ('b08n01', 'i1', 1), ('b08n02', 'i2', 1), ('b08n03', 'float32', 1),
        ('b08n04', 'float32', 1), ('b08n05', 'float64', 1), ('b08n06', 'i2', 1),
        ('b08n07', 'i2', 1), ('b08n08', 'float32', 1), ('b08n09', 'float32', 1),
        ('b08n10', 'S1', 50),
        ('b09n01', 'i1', 1), ('b09n02', 'i2', 1), ('b09n03', 'i2', 1),
        ('b09n04', 'i2', 1), ('b09n05', 'float64', 1), ('b09n06', 'S1', 70),
        ('b10n01', 'i1', 1), ('b10n02', 'i4', 1), ('b10n03', 'i2', 1),
        ('b10n04', 'i2', 1), ('b10n05', 'i2', 1), ('b10n06', 'S1', 36),
        ('b11n01', 'i1', 1), ('b11n02', 'i2', 1), ('b11n03', 'S1', 256),
        ('b12n01', 'i2', res)]


def decode_hsd(file_path):
    """解码HSD文件并返回亮温数据
    参考: /mnt/e/hxcode/polar_satellite/himawari9_hsd2tif.py
    """
    resolution = int(os.path.basename(file_path)[-16])
    band_num = int(os.path.basename(file_path)[-25:-23])

    # 设置分辨率参数
    if resolution == 1:  # R10: 1km
        res, nlin, ncol = 12100000, 1100, 11000
    elif resolution == 2:  # R20: 2km
        res, nlin, ncol = 3025000, 550, 5500
    else:  # R05: 0.5km
        res, nlin, ncol = 48400000, 2200, 22000

    formation = get_formation(res)

    # 解压并读取
    fdn, tmpfile = tempfile.mkstemp()
    try:
        with bz2.BZ2File(file_path, 'rb') as bz2file:
            with closing(os.fdopen(fdn, 'wb')) as ofpt:
                ofpt.write(bz2file.read())
    except (IOError, EOFError):
        os.remove(tmpfile)
        return None

    alldata = np.fromfile(tmpfile, dtype=formation)
    os.remove(tmpfile)

    if alldata['b12n01'].shape[0] != 1:
        return None

    data = alldata['b12n01'].reshape(nlin, ncol)
    radiance = data * alldata['gfcce'][0] + alldata['cfcce'][0]

    # 红外波段转亮温
    if band_num > 6:
        radiance *= 1e6
        lambda1 = alldata['cwl'][0] / 1e6
        h, c, k = alldata['pc'][0], alldata['sol'][0], alldata['bc'][0]
        planck_c1 = 2 * h * c ** 2 / lambda1 ** 5
        planck_c2 = h * c / (k * lambda1)

        result = np.zeros((nlin, ncol), dtype=np.float32)
        mask = radiance > 0
        temp = planck_c2 / np.log(planck_c1 / radiance[mask] + 1.0)
        tbb = alldata['c0'][0] + alldata['c1'][0] * temp + alldata['c2'][0] * temp ** 2
        result[mask] = tbb
        return result
    else:
        # 可见光波段转反射率
        result = np.zeros((nlin, ncol), dtype=np.float32)
        mask = radiance > 0
        result[mask] = radiance[mask] * alldata['c0'][0]
        return result


def merge_blocks(data_dir, datetime_str, band_name, sat_prefix="H08"):
    """合并10块HSD数据"""
    pattern = f"HS_{sat_prefix}_{datetime_str}_B{band_name}_FLDK_*.DAT.bz2"
    files = sorted(glob.glob(os.path.join(data_dir, pattern)))

    if len(files) == 0:
        return None

    # 确定数组大小
    first_data = decode_hsd(files[0])
    if first_data is None:
        return None

    rows, cols = first_data.shape
    merged = np.full((rows * 10, cols), np.nan, dtype=np.float32)

    for file in files:
        block_num = int(os.path.basename(file)[-12:-10])
        data = decode_hsd(file)
        if data is not None:
            merged[(block_num - 1) * rows:block_num * rows, :] = data

    return merged


def scan_h89_data(base_dir):
    """扫描H89目录"""
    data_list = []
    for year in sorted(os.listdir(base_dir)):
        year_dir = os.path.join(base_dir, year)
        if not os.path.isdir(year_dir) or not year.isdigit():
            continue
        for month in sorted(os.listdir(year_dir)):
            month_dir = os.path.join(year_dir, month)
            if not os.path.isdir(month_dir) or not month.isdigit():
                continue
            for day in sorted(os.listdir(month_dir)):
                day_dir = os.path.join(month_dir, day)
                if not os.path.isdir(day_dir) or not day.isdigit():
                    continue
                for hhmm in sorted(os.listdir(day_dir)):
                    time_dir = os.path.join(day_dir, hhmm)
                    if not os.path.isdir(time_dir) or not hhmm.isdigit():
                        continue
                    bz2_files = glob.glob(os.path.join(time_dir, "*.DAT.bz2"))
                    if bz2_files:
                        sat_prefix = os.path.basename(bz2_files[0]).split('_')[1]
                        dt = datetime.strptime(f"{year}{month}{day}_{hhmm}", '%Y%m%d_%H%M')
                        data_list.append({'datetime': dt, 'time_dir': time_dir, 'satellite': sat_prefix})
    return data_list


def read_h89_bands(time_dir, datetime_str, satellite, bands=['13', '15']):
    """读取H89波段数据"""
    band_data = {}
    for band in bands:
        data = merge_blocks(time_dir, datetime_str, band, satellite)
        if data is None:
            return None
        band_data[f'B{band}'] = data
    return band_data


def nom2Gll(val_arr, res_in, res_out, out_bounds, sat_lon=140.7,
             srcnodata=np.nan, dstnodata=np.nan, dtype=gdal.GDT_Float32):
    """将标称投影数据转换为等经纬度投影
    参考: /mnt/e/code/smart3_project/arspy/space_match.py
    """
    if len(val_arr.shape) == 3:
        im_bands, im_height, im_width = val_arr.shape
    else:
        im_bands, (im_height, im_width) = 1, val_arr.shape

    ds = gdal.GetDriverByName('MEM').Create('', im_width, im_height, im_bands, dtype)
    ds.SetGeoTransform([-0.5 * ds.RasterXSize * res_in, res_in, 0,
                        0.5 * ds.RasterYSize * res_in, 0, -res_in])

    srs = osr.SpatialReference()
    srs.ImportFromProj4(f'+proj=geos +h=35785863 +a=6378137.0 +b=6356752.3 +lon_0={sat_lon} +no_defs')
    ds.SetProjection(srs.ExportToWkt())

    if im_bands == 1:
        ds.GetRasterBand(1).WriteArray(val_arr)
    else:
        for i in range(im_bands):
            ds.GetRasterBand(i + 1).WriteArray(val_arr[i])
    ds.FlushCache()

    dst_ds = gdal.Warp('', ds, dstSRS='EPSG:4326', format='MEM', outputType=dtype,
                       outputBounds=out_bounds, xRes=res_out, yRes=res_out,
                       dstNodata=dstnodata, srcNodata=srcnodata,
                       resampleAlg=gdal.GRA_Bilinear)
    im_data_warp = dst_ds.ReadAsArray(0, 0, dst_ds.RasterXSize, dst_ds.RasterYSize)
    del ds
    del dst_ds

    return im_data_warp


def reproject_bands_to_latlon(h89_bands, sat_lon=140.7,
                                 output_bounds=(55.0, -85.0, 225.0, 85.0), res_out=0.02):
    """将H89波段数据重投影到等经纬度"""
    reprojected_bands = {}
    res_in = 2000  # R20分辨率: 2km
    lon_bounds = None
    lat_bounds = None

    for band_name, data in h89_bands.items():
        reprojected = nom2Gll(data, res_in, res_out, output_bounds, sat_lon)
        reprojected_bands[band_name] = reprojected

        # 生成经纬度边界数组
        if lon_bounds is None:
            nlat, nlon = reprojected.shape
            lon_bounds = np.linspace(output_bounds[0], output_bounds[2], nlon)
            lat_bounds = np.linspace(output_bounds[3], output_bounds[1], nlat)

    return reprojected_bands, lon_bounds, lat_bounds
