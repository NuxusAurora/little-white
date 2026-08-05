#!/usr/bin/env bash
# Linux: 一键重建全部动画（抠图 + 尺寸统一）
cd "$(dirname "$0")"
exec python3 build_all.py
