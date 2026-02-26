#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
  @date    : 2024/8/16 9:36
  @author  : baizhaofeng
  @email   : zfengbai@gmail.com
  @file    : qgsmap.py
"""
import os
import glob
import numpy as np
import rioxarray as rxr
import xarray as xr
import geopandas as gpd
from qgis.core import *
from osgeo import gdal
from qgis.PyQt.QtGui import QFont


class QgsMap:
    def __init__(self):
        self.InitMapLayers = {}
        self.layout = None

        # 解决ERROR 6: The PNG driver does not support update access to existing datasets.
        gdal.PushErrorHandler('CPLQuietErrorHandler')
        gdal.SetConfigOption("GDAL_PAM_ENABLED", "NO")

        # create a reference to the QgsApplication, setting the # second argument to False disables the GUI
        self.qgs = QgsApplication([], False)
        # load providers
        self.qgs.initQgis()

    def load(self, template):
        # p1：读取qgs模板文件
        self.project = QgsProject.instance()
        self.project.read(template)

        # 键值对存储图层名称和图层对象
        self.InitMapLayers = {}

        for layer in self.project.mapLayers().values():
            self.InitMapLayers[layer.name()] = layer

        # 获取layout
        layout = self.project.layoutManager().layoutByName("layout")
        # 复制layout
        self.layout = self.project.layoutManager().duplicateLayout(layout=layout, newName="tmp_layout")

    def init_project(self):
        """
初始化工程，还原初始图层
        """
        for layer in self.project.mapLayers().values():
            if layer.name() in self.InitMapLayers:
                root = self.project.layerTreeRoot()
                myrlayer = root.findLayer(layer.id())

                myrlayer.setItemVisibilityChecked(True)
            else:
                self.project.removeMapLayer(layer.id())

    def add_single_band_raster_layer(self, tiffile, index: int = 0):
        """
加载栅格图层，并调整图层顺序,然后渲染图层
        @param tiffile:
        @param index:
        @return:
        """
        # 加载图层
        dataformat = os.path.basename(tiffile).split('.')[1]
        if dataformat in ['TIFF', 'tif']:
            raster_layer = QgsRasterLayer(tiffile)
        else:
            raster_layer = QgsVectorLayer(tiffile, "火点", "ogr")
        self.project.addMapLayer(raster_layer)

        # 修改图层顺序
        if index > 0:
            root = self.project.layerTreeRoot()

            myrlayer = root.findLayer(raster_layer.id())
            rlayclone = myrlayer.clone()
            parent = myrlayer.parent()
            parent.insertChildNode(index, rlayclone)
            parent.removeChildNode(myrlayer)
        return raster_layer

    def render_raster_layer_by_qml(self, raster_layer: QgsRasterLayer, qml_file: str = None):
        """
基于qml文件渲染栅格图层
        @param raster_layer:
        @param qml_file:
        """
        raster_layer.loadNamedStyle(qml_file)
        raster_layer.triggerRepaint()

    def add_mapinfo(self, mapinfo: dict, txt_buffer: bool = False, other: str = ""):
        """
添加：标题、时间、卫星/传感器、分辨率
        @param mapinfo:
        """
        for k, v in mapinfo.items():
            if k == "title":
                v = other + v
            if txt_buffer:
                new_v = "<p style=\"color:#000000;-webkit-text-stroke: 6px white\">%s</p >" % v
            else:
                new_v = v
            self.layout.itemById(k).setText(new_v)

    def add_table_list(self, shpfile):
        gdf = gpd.read_file(shpfile)
        fire_list = [[str(item) for item in row] for row in
                     gdf[["index", "lonlat", "burnedSize"]].head(10).values.tolist()]

        # 添加信息表
        table = QgsLayoutItemTextTable(self.layout)
        self.layout.addMultiFrame(table)

        # Add columns abd fill with data
        fields = ['编号', '经纬度', '热点面积(公顷)']
        cols = [QgsLayoutTableColumn(), QgsLayoutTableColumn(), QgsLayoutTableColumn()]
        for n in range(0, len(fields)):
            cols[n].setHeading(fields[n])

        # content text
        content_text_format = QgsTextFormat()
        content_text_format.setFont(QFont('Times New Roman'))
        content_text_format.setSize(14)
        table.setContentTextFormat(content_text_format)

        # header text
        header_text_format = QgsTextFormat()
        header_text_format.setFont(QFont('KaiTi_GB2312'))
        header_text_format.setSize(14)
        table.setHeaderTextFormat(header_text_format)

        table.setColumns(cols)
        table.setContents(fire_list)

        # Add frame
        frame = QgsLayoutFrame(self.layout, table)

        reference_item = self.layout.itemById("Map 1")
        reference_item_position = reference_item.positionWithUnits()
        reference_item_size = reference_item.sizeWithUnits()

        frame.attemptResize(
            QgsLayoutSize(20, frame.boundingRect().height() * (len(fire_list) + 1) + 1 - reference_item_position.y()),
            True)  # 增加一些边距

        layout_height = reference_item_size.height()
        frame.attemptMove(QgsLayoutPoint(reference_item_position.x(),
                                         reference_item_position.y() + layout_height - frame.boundingRect().height(),
                                         QgsUnitTypes.LayoutMillimeters))
        table.addFrame(frame)
        return

    def add_legend(self, legend_file: str):
        rectangle = self.layout.itemById("colorbar")
        rectangle.setPicturePath(legend_file)

    def set_group_visibility_by_group_name(self, group_name: str, visibility: bool = True):
        """
根据图层组名称，设置图层组的可见性
        @param group_name:
        @param visibility:
        """
        root = self.project.layerTreeRoot()
        for group in root.findGroups():
            if group.name() == group_name:
                group.setItemVisibilityChecked(visibility)
            else:
                group.setItemVisibilityChecked(not visibility)

    def set_legend_visibility_by_group_name(self, group_name: str, visibility: bool = True):
        """
设置图例组的可见性
        @param group_name:
        @param visibility:
        """
        legend_groups = {
            "provice": self.layout.itemById("provice_legend_group"),
            "city": self.layout.itemById("city_legend_group"),
            "xian": self.layout.itemById("xian_legend_group")
        }

        for name, group in legend_groups.items():
            if name == group_name:
                group.setVisibility(visibility)
            else:
                group.setVisibility(not visibility)

    def zoom_to_layer(self, layer: QgsRasterLayer, scale_factor: float = 1.1):
        """
        缩放至图层范围
        @param layer: 要缩放的栅格图层
        @param scale_factor: 缩放因子，1.0为刚好适应，大于1扩大范围，小于1缩小范围
        """
        # 获取图层范围
        extent = layer.extent()

        # 获取地图项
        mapitem = self.layout.itemById("Map1")

        # 坐标转换（如果需要）
        sourceCRS = layer.crs()
        desCRS = mapitem.crs()

        if sourceCRS != desCRS:
            transform = QgsCoordinateTransform(sourceCRS, desCRS, QgsProject.instance())
            extent = transform.transformBoundingBox(extent)

        # 应用缩放因子
        if scale_factor != 1.0:
            extent.scale(scale_factor)

        # 缩放至范围
        mapitem.zoomToExtent(extent)

        return layer

    def zoom_to_selected_feature_extent(self, group_name: str, code: str):
        """
根据图层组名称，行政编码，缩放至该行政区域
        @param group_name:
        @param code:
        """
        # 设置工程变量值
        QgsExpressionContextUtils.setProjectVariable(project=self.project, name='code', value=code)

        # 获得图层组第一个图层,需要注意的是第一个图层和图层组级别要一致,如省图层组第一个图层必须是省图层
        root = self.project.layerTreeRoot()
        map_layer = root.findGroup(group_name).children()[0].layer()
        # 获得图层范围
        map_layer.selectByExpression("code=%s" % code, QgsVectorLayer.SetSelection)

        extent = map_layer.boundingBoxOfSelected()

        sourceCRS = map_layer.crs()

        mapitem = self.layout.itemById("Map 1")
        desCRS = mapitem.crs()

        transform = QgsCoordinateTransform(sourceCRS, desCRS, QgsProject.instance())
        map_extent = transform.transformBoundingBox(extent)

        map_extent.scale(1.1)
        mapitem.zoomToExtent(map_extent)
        return map_layer

    def save(self, png_file: str, png_mini: str = None):
        self.layout.refresh()

        # 输出图片
        exporter = QgsLayoutExporter(self.layout)
        setting = QgsLayoutExporter.ImageExportSettings()
        setting.dpi = 300
        exporter.exportToImage(png_file, setting)

        # 输出压缩图
        if png_mini:
            setting.dpi = 100
            exporter.exportToImage(png_mini, setting)

    def __del__(self):
        if self.layout:
            self.project.layoutManager().removeLayout(self.layout)
            self.layout = None

        if self.qgs:
            self.qgs.closeAllWindows()
            self.qgs = None


class DrawMap(QgsMap):
    def __init__(self):
        super(DrawMap, self).__init__()

    def draw_single_map(self, tiffile: str, pngfile: str, template: str, qmlfile: str, mapinfo: dict, index: int = 2,
                        png_mini: str = None, txt_buffer: bool = False, zoom_to_layer: bool = True, scale_factor: float = 1.1):
        """
绘制单个专题图，即一个TIFF输出一张专题图
        @param tiffile:
        @param pngfile:
        @param template:
        @param qmlfile:
        @param mapinfo:
        @param index:
        @param zoom_to_layer: 是否缩放至图层范围
        @param scale_factor: 缩放因子，1.0为刚好适应，大于1扩大范围
        @return:
        """
        # 加载模板
        self.load(template)
        # 初始化图层
        self.init_project()

        # 渲染图层
        raster_layer = self.add_single_band_raster_layer(tiffile, index)
        self.render_raster_layer_by_qml(raster_layer, qmlfile)

        # 缩放至图层范围
        if zoom_to_layer:
            self.zoom_to_layer(raster_layer, scale_factor)

        # 添加图例
        self.add_legend(qmlfile[:-4] + ".png")
        # 添加制图要素
        self.add_mapinfo(mapinfo, txt_buffer)
        # 输出专题图
        self.save(pngfile, png_mini)


if __name__ == '__main__':
    tiffile = r"D:\data\agms\GPP\20240101POAY\FY3D_MERSI_GLL_NPP_20240101000000_POAY_GLL_ALL_1000M.TIFF"
    tiffile1 = r"D:\data\agms\GPP\20240101POAY\FY3D_MERSI_GLL_GPP_20240101000000_POAY_GLL_ALL_1000M.TIFF"
    pngfile = r"D:\data\agms\GPP\20240101POAY\FY3D_MERSI_GLL_NPP_20240101000000_POAY_GLL_ALL_1000M.PNG"
    pngfile1 = r"D:\data\agms\GPP\20240101POAY\FY3D_MERSI_GLL_GPP_20240101000000_POAY_GLL_ALL_1000M.PNG"
    auxPath = "d:/auxdata/gpp_npp"

    gppinfo = {"title": "卫星总初级生产力产品",
               "date": "2024年",
               "satellite": "卫星/传感器:%s/%s" % ("FY3D", "MERSI"),
               "resolution": "空间分辨率:1000m"}

    draw = DrawMap()

    draw.draw_single_map(tiffile1, pngfile1, os.path.join(auxPath, "china", "template.qgs"),
                         os.path.join(auxPath, "style", "GPP_" + "POAY" + ".qml"), gppinfo, index=14)
