#!/bin/bash
# 保险智能助手 — 重启服务
# 用法: ./restart.sh [mock]
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec bash "$SCRIPT_DIR/start.sh" restart "$@"
