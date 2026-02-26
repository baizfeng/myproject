#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
数据保存模块 - 支持 GeoTIFF 和 NetCDF 格式
"""

import numpy as np
import h5py
import datetime
from osgeo import gdal, osr

gdal.DontUseExceptions()


def save_tiff(data, lon, lat, tiffile, resolution=None, fillvalue=65535, metadata=None):
    """保存为GeoTIFF（等经纬投影）"""
    if data.ndim == 2:
        data = data[np.newaxis, ...]

    n_bands, height, width = data.shape
    if resolution is None:
        resolution = abs(lon[1] - lon[0])

    # 根据数据类型选择GDAL数据类型
    dtype_map = {
        'uint8': gdal.GDT_Byte,
        'uint16': gdal.GDT_UInt16,
        'int16': gdal.GDT_Int16,
        'uint32': gdal.GDT_UInt32,
        'int32': gdal.GDT_Int32,
        'float32': gdal.GDT_Float32,
        'float64': gdal.GDT_Float64
    }

    first_band_dtype = data[0].dtype if hasattr(data[0], 'dtype') else np.float32
    gdal_dtype = dtype_map.get(first_band_dtype.name, gdal.GDT_Float32)

    ds = gdal.GetDriverByName("GTiff").Create(tiffile, width, height, n_bands, gdal_dtype,
                                              options=['COMPRESS=LZW', 'TILED=YES'])
    ds.SetGeoTransform([lon[0], float(resolution), 0, lat[0], 0, -float(resolution)])

    ssr = osr.SpatialReference()
    ssr.ImportFromEPSG(4326)
    ds.SetProjection(ssr.ExportToWkt())

    for i in range(n_bands):
        band = ds.GetRasterBand(i + 1)
        band.WriteArray(data[i])
        if metadata and i < len(metadata):
            meta = metadata[i]
            band.SetNoDataValue(meta.get('fillvalue', fillvalue))
            band.SetDescription(meta['description'])
            if meta.get('wavelength'):
                band.SetMetadataItem('WAVELENGTH', str(meta['wavelength']))
            band.SetMetadataItem('BAND_NAME', meta['name'])
            band.SetMetadataItem('SCALE_FACTOR', str(meta['scale']))
            if meta.get('offset'):
                band.SetMetadataItem('OFFSET', str(meta['offset']))
            band.SetMetadataItem('UNIT', meta['unit'])
        else:
            band.SetNoDataValue(fillvalue)

    ds.FlushCache()
    del ds


def save_netcdf(data_dict, lon, lat, ncfile, var_attrs=None, global_attrs=None):
    """保存为NetCDF（等经纬投影）

    参数:
        data_dict: 数据字典 {'IR': 3D, 'LandSeaMask': 2D, ...}
        lon: 经度数组 [width]
        lat: 纬度数组 [height]
        ncfile: 输出文件路径
        var_attrs: 变量属性字典，如 {'IR': {'long_name': '...', 'units': '...'}}
        global_attrs: 全局属性字典
    """
    h5fid = h5py.File(ncfile, 'w')

    # 添加坐标
    lat_ds = h5fid.create_dataset("latitude", data=lat)
    lat_ds.attrs["long_name"] = 'Latitude'
    lat_ds.attrs["units"] = 'degrees_north'

    lon_ds = h5fid.create_dataset("longitude", data=lon)
    lon_ds.attrs["long_name"] = 'Longitude'
    lon_ds.attrs["units"] = 'degrees_east'

    # 添加数据变量
    for var_name, var_data in data_dict.items():
        # 根据输入数据的实际类型创建dataset，不强制转换为float32
        dtype = var_data.dtype if var_data.dtype != np.float64 else np.float32
        ds = h5fid.create_dataset(var_name, data=var_data, dtype=dtype, chunks=True, compression='gzip')
        if var_attrs and var_name in var_attrs:
            for key, val in var_attrs[var_name].items():
                ds.attrs[key] = str(val)
        else:
            ds.attrs['_FillValue'] = '65535'
        # 关联维度 - 使用正索引
        if var_data.ndim == 3:
            h5fid.create_dataset(f"{var_name}_channel", data=np.arange(var_data.shape[0]))
            ds.dims[0].label = f"{var_name}_channel"
            ds.dims[1].attach_scale(lat_ds)
            ds.dims[2].attach_scale(lon_ds)
        else:  # 2D
            ds.dims[0].attach_scale(lat_ds)
            ds.dims[1].attach_scale(lon_ds)

    # 全局属性
    if global_attrs:
        for key, val in global_attrs.items():
            h5fid.attrs[key] = str(val)

    h5fid.close()
