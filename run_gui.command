#!/bin/bash
cd "$(dirname "$0")"

caffeinate -i -s ./.venv/bin/python gui.py
read -p "Nhan Enter de dong..."
