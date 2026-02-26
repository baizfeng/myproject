#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
算法入口文件 - 使用新的简洁接口
"""

import os
import sys
import time
import json
import traceback

# 添加arspy路径（自动查找arspy目录）
_current_dir = os.path.dirname(os.path.abspath(__file__))
_arspy_path = os.path.join(_current_dir, "..")
if _arspy_path not in sys.path:
    sys.path.insert(0, _arspy_path)

# 导入配置
from config import algorithm_name, key_steps, INPUT

# 导入简洁接口
from arspy.logger import init, set_status, log, rjson

# 导入主算法
from src.main import main


def run_algorithm(jsonfile):
    """
    执行算法

    参数:
        jsonfile: 输入JSON文件
    """
    start_time = time.time()

    # 读取输入配置
    log(f"读取输入文件: {jsonfile}")
    with open(jsonfile, "rb") as f:
        input_config = json.load(f)

    log("输入json路径内容为:\n" + str(input_config))
    # 初始化全局日志接口
    init(
        result_json_file=input_config.get("resultJsonFile", ""),
        flow_json_file=input_config.get("resultFlowFile", ""),
        log_file=input_config.get("resultLogFile", ""),
        alg_name=algorithm_name,
        key_steps=key_steps
    )

    try:
        # 记录开始
        log(f"算法 {algorithm_name} 开始执行")

        # 提取输入参数（只传INPUT定义的字段给main函数）
        input_fields = [item.split(":", 1)[0] if ":" in item else item for item in INPUT]
        input_params = [input_config.get(label) for label in input_fields]

        # 执行主算法
        main(*input_params)

        # 成功完成
        set_status("0", f"{algorithm_name} 执行成功")
        end_time = time.time()
        cost_time = end_time - start_time
        log(f"算法执行成功，总用时: {cost_time:.2f}秒")

    except KeyError as e:
        log(f"参数错误: {str(e)}")
        set_status("2", f"参数传入异常: {str(e)}")

    except FileNotFoundError as e:
        log(f"文件未找到: {str(e)}")
        set_status("6", f"静态数据异常: {str(e)}")

    except Exception as e:
        log(f"算法执行异常: {str(e)}")
        log(traceback.format_exc())
        set_status("1", f"算法执行失败: {str(e)}")

    finally:
        # 保存结果
        rjson()
        log("结果文件已保存")


if __name__ == '__main__':
    # 获取输入JSON路径
    if len(sys.argv) > 1:
        jsonfile = sys.argv[1]
    else:
        # 默认测试文件
        jsonfile = "/mnt/e/hxcode/polar/polar_l1/test.json"

    # 执行算法
    run_algorithm(jsonfile)
