#!/bin/bash
# 保险智能助手 — 停止服务
# 用法: ./stop.sh
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/start.sh" stop "$@"
