#!/bin/bash
cd "$(dirname "$0")"
./.venv/bin/python main.py
read -p "Nhấn Enter để đóng cửa sổ..."
