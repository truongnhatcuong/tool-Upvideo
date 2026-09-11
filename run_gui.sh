#!/bin/bash
cd "$(dirname "$0")"

echo "Đang khởi động giao diện... Vui lòng đợi trong giây lát!"
./.venv/bin/python gui.py
