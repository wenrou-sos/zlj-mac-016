#!/bin/bash
# 启动大棚种植管理系统
cd "$(dirname "$0")/backend"
exec python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
