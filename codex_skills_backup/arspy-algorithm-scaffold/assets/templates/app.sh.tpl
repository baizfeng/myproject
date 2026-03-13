#!/usr/bin/env bash

export QT_QPA_PLATFORM=offscreen

script_dir="$(cd "$(dirname "$0")"; pwd)"
cd "${script_dir}"

python app.py "$1"
