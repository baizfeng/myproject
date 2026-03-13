#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""算法入口文件 - 自动生成脚手架"""

import json
import os
import sys
import time
import traceback

_current_dir = os.path.dirname(os.path.abspath(__file__))
_arspy_path = os.path.join(_current_dir, "..")
if _arspy_path not in sys.path:
    sys.path.insert(0, _arspy_path)

from config import INPUT, algorithm_name, key_steps
from arspy.logger import init, log, rjson, set_status
from src.main import main


def run_algorithm(jsonfile):
    start_time = time.time()
    log(f"读取输入文件: {jsonfile}")

    with open(jsonfile, "rb") as f:
        input_config = json.load(f)

    init(
        result_json_file=input_config.get("resultJsonFile", ""),
        flow_json_file=input_config.get("resultFlowFile", ""),
        log_file=input_config.get("resultLogFile", ""),
        alg_name=algorithm_name,
        key_steps=key_steps,
    )

    try:
        log(f"算法 {algorithm_name} 开始执行")
        input_fields = [item.split(":", 1)[0] if ":" in item else item for item in INPUT]
        input_params = [input_config.get(label) for label in input_fields]
        main(*input_params)

        set_status("0", f"{algorithm_name} 执行成功")
        log(f"算法执行成功，总用时: {time.time() - start_time:.2f}秒")
    except KeyError as e:
        log(f"参数错误: {e}")
        set_status("2", f"参数传入异常: {e}")
    except FileNotFoundError as e:
        log(f"文件未找到: {e}")
        set_status("6", f"静态数据异常: {e}")
    except Exception as e:
        log(f"算法执行异常: {e}")
        log(traceback.format_exc())
        set_status("1", f"算法执行失败: {e}")
    finally:
        rjson()
        log("结果文件已保存")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        input_json = sys.argv[1]
    else:
        input_json = "test.json"

    run_algorithm(input_json)
