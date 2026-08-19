#!/bin/bash
# ────────────────────────────────────────────────
# 保险智能助手 — 一键管理脚本
# 用法:
#   ./start.sh start [mock]   — 启动服务（mock 可选）
#   ./start.sh stop            — 停止服务（含 Studio）
#   ./start.sh restart [mock]  — 重启服务
#   ./start.sh status          — 查看服务状态
#   ./start.sh studio          — 单独启动 LangGraph Studio（调试用）
# ────────────────────────────────────────────────

set -o pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$PROJECT_DIR"

PYTHON=/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13
BACKEND_PORT=8000
FRONTEND_PORT=5173
STUDIO_PORT=2024
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$PID_DIR" "$LOG_DIR"

BACKEND_PID_FILE="$PID_DIR/backend.pid"
FRONTEND_PID_FILE="$PID_DIR/frontend.pid"
STUDIO_PID_FILE="$PID_DIR/studio.pid"

STUDIO_BIN="$PROJECT_DIR/.venv/bin/langgraph"
STUDIO_CMD=(dev --no-browser --allow-blocking)
STUDIO_URL="https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:$STUDIO_PORT"

# ── 工具函数 ──────────────────────────────────────

is_running() {
    local pid_file=$1
    if [ -f "$pid_file" ]; then
        local pid=$(cat "$pid_file")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

kill_port() {
    local port=$1
    local pids=$(lsof -ti:$port 2>/dev/null || true)
    if [ -n "$pids" ]; then
        echo "  清理端口 $port 进程: $pids"
        echo "$pids" | xargs kill -9 2>/dev/null || true
    fi
}

# ── 检查依赖 ──────────────────────────────────────

check_deps() {
    echo "📦 检查 Python 依赖..."
    $PYTHON -c "import fastapi, langgraph, sse_starlette" 2>/dev/null || {
        echo "  安装基础依赖..."
        $PYTHON -m pip install fastapi uvicorn langgraph sse-starlette pydantic pydantic-settings bcrypt pyjwt python-jose passlib httpx 2>/dev/null
    }
    $PYTHON -c "import langgraph.checkpoint.sqlite" 2>/dev/null || {
        echo "  安装 SQLite checkpointer..."
        $PYTHON -m pip install langgraph-checkpoint-sqlite 2>/dev/null
    }
    $PYTHON -c "import chromadb" 2>/dev/null || {
        echo "  安装 ChromaDB..."
        $PYTHON -m pip install chromadb 2>/dev/null
    }
    $PYTHON -c "import rank_bm25" 2>/dev/null || {
        echo "  安装 rank-bm25..."
        $PYTHON -m pip install rank-bm25 2>/dev/null
    }
}

check_frontend() {
    if [ ! -d "frontend/node_modules" ]; then
        echo "📦 安装前端依赖..."
        cd frontend && npm install && cd ..
    fi
}

# ── Studio (LangGraph 调试) ─────────────────────

do_studio_start() {
    if is_running "$STUDIO_PID_FILE"; then
        echo "⚠️  Studio 已在运行 (PID: $(cat "$STUDIO_PID_FILE"))"
        return 0
    fi

    if [ ! -x "$STUDIO_BIN" ]; then
        echo "⚠️  未找到 $STUDIO_BIN，跳过 Studio 启动"
        echo "   安装: uv pip install --python .venv/bin/python 'langgraph-cli[inmem]'"
        return 0
    fi

    echo "🛑 清理 Studio 端口..."
    kill_port $STUDIO_PORT
    echo "🚀 启动 LangGraph Studio (端口: $STUDIO_PORT)..."
    nohup "$STUDIO_BIN" "${STUDIO_CMD[@]}" > "$LOG_DIR/studio.log" 2>&1 &
    echo $! > "$STUDIO_PID_FILE"
    sleep 2
    echo "  Studio PID: $(cat "$STUDIO_PID_FILE")"
    echo "  Studio UI:  $STUDIO_URL"
}

do_studio_stop() {
    if is_running "$STUDIO_PID_FILE"; then
        local pid=$(cat "$STUDIO_PID_FILE")
        echo "  停止 Studio (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$STUDIO_PID_FILE"
    fi
    # 兜底：langgraph dev 会 fork API server 子进程，清理所有残留
    pkill -9 -f "langgraph dev" 2>/dev/null || true
    kill_port $STUDIO_PORT
}

# ── 启动 ──────────────────────────────────────────

do_start() {
    local mock_mode=${1:-false}

    if is_running "$BACKEND_PID_FILE"; then
        echo "⚠️  后端已在运行 (PID: $(cat "$BACKEND_PID_FILE"))"
    else
        echo "🛑 清理后端端口..."
        kill_port $BACKEND_PORT
        echo "🚀 启动后端服务 (端口: $BACKEND_PORT)..."

        local env_prefix=""
        if [ "$mock_mode" = "true" ]; then
            env_prefix="POLICY_AGENT_MOCK_LLM=true"
        fi

        $PYTHON -c "
import os, subprocess, time
env = os.environ.copy()
$([ "$mock_mode" = "true" ] && echo "env['POLICY_AGENT_MOCK_LLM'] = 'true'" || echo "")
proc = subprocess.Popen(
    ['$PYTHON', '-m', 'uvicorn', 'backend.main:app', '--host', '0.0.0.0', '--port', '$BACKEND_PORT'],
    cwd='$PROJECT_DIR',
    env=env,
    stdout=open('$LOG_DIR/backend.log', 'a'),
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
with open('$BACKEND_PID_FILE', 'w') as f:
    f.write(str(proc.pid))
for i in range(20):
    time.sleep(1)
    try:
        import urllib.request
        r = urllib.request.urlopen('http://localhost:$BACKEND_PORT/health', timeout=1)
        if r.status == 200:
            break
    except:
        pass
" 2>/dev/null &
        sleep 1
        echo "  后端 PID: $(cat "$BACKEND_PID_FILE" 2>/dev/null || echo 'unknown')"
    fi

    if is_running "$FRONTEND_PID_FILE"; then
        echo "⚠️  前端已在运行 (PID: $(cat "$FRONTEND_PID_FILE"))"
    else
        echo "🛑 清理前端端口..."
        kill_port $FRONTEND_PORT
        echo "🚀 启动前端开发服务 (端口: $FRONTEND_PORT)..."

        $PYTHON -c "
import subprocess, time
proc = subprocess.Popen(
    ['npm', 'run', 'dev'],
    cwd='$PROJECT_DIR/frontend',
    stdout=open('$LOG_DIR/frontend.log', 'a'),
    stderr=subprocess.STDOUT,
    start_new_session=True,
)
with open('$FRONTEND_PID_FILE', 'w') as f:
    f.write(str(proc.pid))
" 2>/dev/null &
        sleep 1
        echo "  前端 PID: $(cat "$FRONTEND_PID_FILE" 2>/dev/null || echo 'unknown')"
    fi

    # 等待后端就绪
    echo "⏳ 等待后端就绪..."
    local max_wait=20
    local waited=0
    while [ $waited -lt $max_wait ]; do
        if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
            echo "✅ 后端已就绪"
            break
        fi
        sleep 1
        waited=$((waited + 1))
    done

    if [ $waited -ge $max_wait ]; then
        echo "⚠️  后端启动超时"
        echo "  查看日志: tail -f $LOG_DIR/backend.log"
    fi

    echo ""

    # 顺带启动 LangGraph Studio（调试用，失败不影响主服务）
    do_studio_start

    echo ""
    echo "══════════════════════════════════════════"
    echo "  ✅ 启动完成！"
    echo ""
    echo "  前端:  http://localhost:$FRONTEND_PORT"
    echo "  后端:  http://localhost:$BACKEND_PORT"
    echo "  API:   http://localhost:$BACKEND_PORT/docs"
    echo "  Studio: $STUDIO_URL"
    echo ""
    echo "  默认账号: admin / admin"
    echo "  会话存储: data/checkpoints.sqlite"
    echo "  向量存储: data/chroma/"
    echo "  日志:     logs/"
    echo "══════════════════════════════════════════"
}

# ── 停止 ──────────────────────────────────────────

do_stop() {
    echo "🛑 停止服务..."

    if is_running "$BACKEND_PID_FILE"; then
        local pid=$(cat "$BACKEND_PID_FILE")
        echo "  停止后端 (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$BACKEND_PID_FILE"
    else
        echo "  后端未在运行"
    fi

    if is_running "$FRONTEND_PID_FILE"; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        echo "  停止前端 (PID: $pid)..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
        rm -f "$FRONTEND_PID_FILE"
    else
        echo "  前端未在运行"
    fi

    # Studio（若在运行）
    do_studio_stop

    # 兜底清理
    kill_port $BACKEND_PORT
    kill_port $FRONTEND_PORT

    echo "✅ 服务已停止"
}

# ── 状态 ──────────────────────────────────────────

do_status() {
    local backend_ok=false
    local frontend_ok=false

    if is_running "$BACKEND_PID_FILE"; then
        local pid=$(cat "$BACKEND_PID_FILE")
        if curl -s http://localhost:$BACKEND_PORT/health > /dev/null 2>&1; then
            backend_ok=true
            echo "✅ 后端运行中 (PID: $pid, 端口: $BACKEND_PORT)"
        else
            echo "⚠️  后端进程存在但未就绪 (PID: $pid)"
        fi
    else
        echo "❌ 后端未运行"
    fi

    if is_running "$FRONTEND_PID_FILE"; then
        local pid=$(cat "$FRONTEND_PID_FILE")
        echo "✅ 前端运行中 (PID: $pid, 端口: $FRONTEND_PORT)"
        frontend_ok=true
    else
        echo "❌ 前端未运行"
    fi

    if is_running "$STUDIO_PID_FILE"; then
        local pid=$(cat "$STUDIO_PID_FILE")
        echo "✅ Studio 运行中 (PID: $pid, 端口: $STUDIO_PORT)"
        echo "   $STUDIO_URL"
    else
        echo "❌ Studio 未运行"
    fi

    # 数据存储状态
    local sqlite_size=0
    if [ -f "$PROJECT_DIR/data/checkpoints.sqlite" ]; then
        sqlite_size=$(du -h "$PROJECT_DIR/data/checkpoints.sqlite" | cut -f1)
        echo "💾  SQLite 会话存储: data/checkpoints.sqlite ($sqlite_size)"
    else
        echo "💾  SQLite 会话存储: 未创建"
    fi

    if [ -d "$PROJECT_DIR/data/chroma" ]; then
        local chroma_size=$(du -sh "$PROJECT_DIR/data/chroma" 2>/dev/null | cut -f1)
        echo "💾  Chroma 向量存储: data/chroma/ ($chroma_size)"
    else
        echo "💾  Chroma 向量存储: 未创建"
    fi
}

# ── 主入口 ────────────────────────────────────────

ACTION="${1:-start}"
MOCK="${2:-false}"

if [ "$MOCK" = "mock" ]; then
    MOCK=true
fi

case "$ACTION" in
    start)
        echo "══════════════════════════════════════════"
        echo "  保险智能助手 — 启动服务"
        if [ "$MOCK" = "true" ]; then
            echo "  模式: Mock LLM (离线测试)"
        else
            echo "  模式: 真实 LLM (Ollama + DeepSeek)"
        fi
        echo "══════════════════════════════════════════"
        check_deps
        check_frontend
        do_start "$MOCK"
        ;;
    stop)
        do_stop
        ;;
    restart)
        echo "══════════════════════════════════════════"
        echo "  保险智能助手 — 重启服务"
        echo "══════════════════════════════════════════"
        do_stop
        sleep 2
        check_deps
        check_frontend
        do_start "$MOCK"
        ;;
    status)
        do_status
        ;;
    studio)
        echo "══════════════════════════════════════════"
        echo "  保险智能助手 — 启动 LangGraph Studio"
        echo "══════════════════════════════════════════"
        do_studio_start
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|studio} [mock]"
        echo ""
        echo "  start [mock]   启动服务 (mock = 离线测试模式)"
        echo "  stop            停止服务（含 Studio）"
        echo "  restart [mock]  重启服务"
        echo "  status          查看运行状态"
        echo "  studio          单独启动 LangGraph Studio（调试用）"
        exit 1
        ;;
esac
