#!/usr/bin/env bash
# Linux: 启动桌宠
cd "$(dirname "$0")"

# 自动启用 dogs conda 环境
if command -v conda >/dev/null 2>&1; then
    source "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate dogs
fi

exec python3 pet.py
