from pyhdf.SD import SD, SDC
import numpy as np

hdf = SD("/mnt/e/CAL_LID_L2_05kmCLay-Standard-V4-51.2023-01-01T04-38-40ZN.hdf", SDC.READ)

# 经纬度取中心点（第1列，而非第0列）
lat = hdf.select("Latitude")[:, 1]  # (3648,)
lon = hdf.select("Longitude")[:, 1]  # (3648,)

num_layers = hdf.select("Number_Layers_Found")[:, 0]  # (3648,)
cad_score = hdf.select("CAD_Score")[:, 0]  # (3648,) 第0层
opacity_flag = hdf.select("Opacity_Flag")[:, 0]  # (3648,) 第0层
layer_temp = hdf.select("Layer_Top_Temperature")[:, 0]  # (3648,) 第0层
layer_top = hdf.select("Layer_Top_Altitude")[:, 0]  # (3648,) 第0层

# 综合质量筛选（修正版）
mask = (
    (num_layers >= 1)  # 有云
    & (cad_score > 20)  # 确认为云
    & (opacity_flag == 1)  # 不透明云（填充值99已被排除）
    & (layer_temp > -9999)  # 有效温度
    & (layer_top > -9999)  # 有效高度
)

# 严格版：仅单层云
strict_mask = mask & (num_layers == 1)

cth_temp = layer_temp[strict_mask]
cth_alt = layer_top[strict_mask]
match_lat = lat[strict_mask]
match_lon = lon[strict_mask]

print(f"总廓线数: {len(lat)}")  # 应为 3648
print(f"宽松筛选样本数: {mask.sum()}")
print(f"严格筛选样本数: {strict_mask.sum()}")
