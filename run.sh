#!/bin/bash
# 保险智能助手 — 启动服务
# 用法: ./run.sh start [mock] | stop | restart [mock] | status
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/start.sh" "$@"
