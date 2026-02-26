#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
全局日志和结果输出接口
像print一样简单使用，无需声明变量
"""

import json
import os
import datetime
from threading import Lock

# 全局锁，确保线程安全
_lock = Lock()

# 全局接口对象
_rjson = None  # 结果JSON接口
_fjson = None  # 流程JSON接口
_log_file = None  # 日志文件路径


def init(result_json_file, flow_json_file, log_file, alg_name, key_steps):
    """
    初始化全局日志接口

    参数:
        result_json_file: 结果JSON文件路径
        flow_json_file: 流程JSON文件路径
        log_file: 日志文件路径
        alg_name: 算法名称
        key_steps: 关键步骤列表
    """
    global _rjson, _fjson, _log_file

    with _lock:
        _rjson = _ResultJson(result_json_file)
        _fjson = _FlowJson(alg_name, key_steps, flow_json_file, log_file)
        _log_file = log_file


# ==================== 结果输出接口 ====================

def set_status(code, message):
    """
    设置算法执行状态

    状态码:
        0: 成功
        1: 失败
        2: 参数错误
        3: 时间异常
        4: 空间异常
        5: 数据损坏
        6: 静态数据错误
        7: 无效数据
    """
    if _rjson:
        _rjson.set_status(code, message)


def add_result(file_path, product_id_eng, product_id_chn, level, format_type):
    """添加输出产品"""
    if _rjson:
        _rjson.add_result(file_path, product_id_eng, product_id_chn, level, format_type)


def set_metadata(satellite, sensor):
    """设置卫星和传感器元数据"""
    if _rjson:
        _rjson.set_metadata(satellite, sensor)


def set_coordinates(resolution, min_lon, min_lat, max_lon, max_lat):
    """设置坐标范围"""
    if _rjson:
        _rjson.set_coordinates(resolution, min_lon, min_lat, max_lon, max_lat)


def set_observation_time(start_time, end_time):
    """设置观测时间"""
    if _rjson:
        _rjson.set_observation_time(start_time, end_time)


def add_custom_field(key, value):
    """添加自定义字段"""
    if _rjson:
        _rjson.add_field(key, value)


# ==================== 流程和日志接口 ====================

def fjson(message, status='0'):
    """
    记录关键步骤执行情况

    参数:
        message: 步骤信息
        status: 状态码 ('0'=成功, '2'=跳过)
    """
    if _fjson:
        _fjson.record_step(message, status)


def log(message):
    """
    输出日志信息（类似print，但会同时写入文件）

    使用示例:
        log("开始处理数据")
        log(f"处理了{count}个文件")
    """
    if _fjson:
        _fjson.write_log(message)
    else:
        # 如果未初始化，直接打印
        timestamp = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S CST")
        print(f"{timestamp}: {message}")


def rjson():
    """保存所有结果到文件"""
    if _rjson:
        _rjson.save()


class _RJsonHelper:
    """结果JSON辅助类，提供便捷的批量添加接口"""

    def __init__(self):
        pass  # 不再存储_rjson引用，而是动态获取

    @property
    def _rjson(self):
        """动态获取当前的_rjson"""
        return _rjson

    def info(self, names=None, result_path=None,
             product_id_eng=None, product_id_chn=None, product_level="L1", **kwargs):
        """
        一键将多个参数添加到resultjson中，并自动保存

        参数:
            names: 文件名字典，如 {"NC": path, "TIFF": path, "PNG.IR11": path}
            result_path: 结果文件根路径，保存时会从路径中移除
            product_id_eng: 产品英文名称，用于所有输出文件
            product_id_chn: 产品中文名称，用于所有输出文件
            product_level: 产品级别，默认"L1"
            **kwargs: 其他键值对，如 satellite="FY3D", sensor="MERSI"

        使用示例:
            rjson.info(names, result_path=resultPath, product_id_eng="IR", product_id_chn="红外",
                       satellite=params['satellite'], sensor=params['sensor'])
        """
        if not self._rjson:
            return

        # 当级别是L1时，productIdENG和productIdCHN使用级别值
        if product_level == "L1":
            default_pid_eng = "L1"
            default_pid_chn = "L1数据"
        else:
            default_pid_eng = None
            default_pid_chn = None

        # 处理names字典
        if names:
            for key, value in names.items():
                if isinstance(value, dict):
                    # 跳过mapinfo字典
                    continue
                elif key.startswith("PNG"):
                    # PNG文件，添加到result
                    band_name = key.replace("PNG", "")
                    pid_eng = product_id_eng if product_id_eng else (default_pid_eng if default_pid_eng else band_name)
                    pid_chn = product_id_chn if product_id_chn else (default_pid_chn if default_pid_chn else band_name)
                    file_path = self._remove_root_path(value, result_path) if result_path else value
                    self._rjson.add_result(
                        file_path=file_path,
                        product_id_eng=pid_eng,
                        product_id_chn=pid_chn,
                        level=product_level,
                        format_type="PNG"
                    )
                elif key == "NC":
                    # NC文件，添加到result
                    pid_eng = product_id_eng if product_id_eng else (default_pid_eng if default_pid_eng else "NC")
                    pid_chn = product_id_chn if product_id_chn else (default_pid_chn if default_pid_chn else "NC")
                    file_path = self._remove_root_path(value, result_path) if result_path else value
                    self._rjson.add_result(
                        file_path=file_path,
                        product_id_eng=pid_eng,
                        product_id_chn=pid_chn,
                        level=product_level,
                        format_type="NC"
                    )
                elif key == "TIFF":
                    # TIFF文件，添加到result
                    pid_eng = product_id_eng if product_id_eng else (default_pid_eng if default_pid_eng else "TIFF")
                    pid_chn = product_id_chn if product_id_chn else (default_pid_chn if default_pid_chn else "TIFF")
                    file_path = self._remove_root_path(value, result_path) if result_path else value
                    self._rjson.add_result(
                        file_path=file_path,
                        product_id_eng=pid_eng,
                        product_id_chn=pid_chn,
                        level=product_level,
                        format_type="TIFF"
                    )
                else:
                    # 其他键直接添加
                    self._rjson.add_field(key, value)

        # 处理其他kwargs参数
        for key, value in kwargs.items():
            self._rjson.add_field(key, value)

        # 自动保存
        self._rjson.save()

    def _remove_root_path(self, full_path, root_path):
        """移除路径中的根路径部分"""
        if not root_path:
            return "/" + full_path.replace("\\", "/").lstrip("/")
        # 统一路径格式
        full_path = full_path.replace('\\', '/')
        root_path = root_path.replace('\\', '/')
        # 移除根路径，并确保以/开头
        if full_path.startswith(root_path):
            return "/" + full_path[len(root_path):].lstrip("/")
        # 如果不匹配，直接返回以/开头的路径
        return "/" + full_path.lstrip("/")

    def save(self):
        """保存所有结果到文件"""
        if self._rjson:
            self._rjson.save()


# 创建全局helper实例
_rjson_helper = _RJsonHelper()


# ==================== 内部实现类 ====================

class _ResultJson:
    """结果JSON内部实现"""

    def __init__(self, filename):
        self.filename = filename
        self.data = {
            "status": "",
            "message": "",
            "productionTime": (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S CST"),
            "result": []
        }

    def set_status(self, code, message):
        self.data['status'] = code
        self.data['message'] = message

    def add_result(self, file_path, product_id_eng, product_id_chn, level, format_type):
        self.data["result"].append({
            "filePath": file_path,
            "productIdENG": product_id_eng,
            "productIdCHN": product_id_chn,
            "productLevel": level,
            "productFormat": format_type
        })

    def set_metadata(self, satellite, sensor):
        self.data["satellite"] = satellite
        self.data["sensor"] = sensor

    def set_coordinates(self, resolution, min_lon, min_lat, max_lon, max_lat):
        self.data["resolution"] = resolution
        self.data["bottomLeftLongitude"] = min_lon
        self.data["topLeftLongitude"] = min_lon
        self.data["bottomLeftLatitude"] = min_lat
        self.data["bottomRightLatitude"] = min_lat
        self.data["topRightLongitude"] = max_lon
        self.data["bottomRightLongitude"] = max_lon
        self.data["topLeftLatitude"] = max_lat
        self.data["topRightLatitude"] = max_lat

    def set_observation_time(self, start_time, end_time):
        self.data["obsStartTime"] = start_time
        self.data["obsEndTime"] = end_time

    def add_field(self, key, value):
        self.data[key] = value

    def save(self):
        file_dir = os.path.dirname(self.filename)
        if not os.path.isdir(file_dir):
            os.makedirs(file_dir, exist_ok=True)

        with open(self.filename, "w", encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)


class _FlowJson:
    """流程JSON内部实现"""

    def __init__(self, product_name, key_steps, out_json_file, log_file):
        self.filename = out_json_file
        self.logfilename = log_file
        self.step_count = 0
        self.total_steps = len(key_steps)

        # 初始化步骤数据
        self.data = {
            "product": product_name,
            "step": [
                {
                    "stepName": step,
                    "stepNo": str(i),
                    "status": "255",
                    "log": "",
                    "timeStamp": ""
                }
                for i, step in enumerate(key_steps)
            ]
        }

        # 创建目录并写入初始文件
        file_dir = os.path.dirname(out_json_file)
        if not os.path.isdir(file_dir):
            os.makedirs(file_dir, exist_ok=True)

        with open(out_json_file, "w", encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

    def record_step(self, message, code_id='0'):
        """记录步骤"""
        if self.step_count >= self.total_steps:
            print(f"警告: 步骤记录次数({self.step_count + 1})超过配置数量({self.total_steps})")
            return

        with open(self.filename, "r+", encoding="utf-8") as f:
            item = json.load(f)
            content = item["step"]

            content[self.step_count]["status"] = code_id
            content[self.step_count]["log"] = message
            content[self.step_count]["timeStamp"] = (
                datetime.datetime.utcnow() + datetime.timedelta(hours=8)
            ).strftime("%Y-%m-%d %H:%M:%S CST")

            f.seek(0)
            f.write(json.dumps(item, ensure_ascii=False, indent=4))
            f.truncate()

        self.step_count += 1
        self.write_log(message)

    def write_log(self, message):
        """写入日志文件"""
        timestamp = (datetime.datetime.utcnow() + datetime.timedelta(hours=8)).strftime("%Y-%m-%d %H:%M:%S CST")
        log_message = f"{timestamp}: {message}\n"

        print(log_message, end='')

        file_dir = os.path.dirname(self.logfilename)
        if not os.path.isdir(file_dir):
            os.makedirs(file_dir, exist_ok=True)

        with open(self.logfilename, 'a+', encoding='utf-8') as f:
            f.write(log_message)
