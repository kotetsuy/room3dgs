#!/usr/bin/env bash
# room3dgs — 起動スクリプト
#
# FastAPI サーバ（uvicorn）を 127.0.0.1:8000 でバックグラウンド起動する。
# 再構成本体（WorldMirror infer.py）は各リクエストごとに server 内から
# サブプロセス実行されるため、常駐させるのはこの 1 プロセスのみ。
#
# 使い方:  ./start_all.sh          # 既定 127.0.0.1:8000 で起動
#          HOST=0.0.0.0 PORT=9000 ./start_all.sh
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
VENV_UVICORN=".venv/bin/uvicorn"
PID_FILE="run/server.pid"
LOG_FILE="run/server.log"

mkdir -p run

# --- 既に起動していないか確認 ---
if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "既に起動しています (PID $(cat "$PID_FILE"))。停止するには ./stop_all.sh"
    echo "  → http://${HOST}:${PORT}/"
    exit 0
fi
rm -f "$PID_FILE"

if [[ ! -x "$VENV_UVICORN" ]]; then
    echo "エラー: $VENV_UVICORN が見つかりません。先に依存をインストールしてください:" >&2
    echo "  python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt" >&2
    exit 1
fi

# --- 起動 ---
echo "room3dgs サーバを起動します: http://${HOST}:${PORT}/"
nohup "$VENV_UVICORN" server:app --host "$HOST" --port "$PORT" \
    >> "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

# 起動確認（数秒待って生存チェック）
sleep 2
if kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
    echo "起動しました (PID $(cat "$PID_FILE"))  ログ: $LOG_FILE"
    echo "Chrome で http://${HOST}:${PORT}/ を開いてください。"
else
    echo "起動に失敗しました。ログを確認してください: $LOG_FILE" >&2
    rm -f "$PID_FILE"
    tail -n 20 "$LOG_FILE" >&2 || true
    exit 1
fi
