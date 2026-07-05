#!/usr/bin/env bash
# room3dgs — 停止スクリプト
#
# start_all.sh が起動した uvicorn サーバを PID ファイルから停止する。
# 進行中の再構成サブプロセス（infer.py）があればサーバと共に終了する。
#
# 使い方:  ./stop_all.sh
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

PID_FILE="run/server.pid"

if [[ ! -f "$PID_FILE" ]]; then
    echo "PID ファイルがありません。起動していないようです。"
    # 念のため取りこぼしプロセスを探す
    if pgrep -f "uvicorn server:app" >/dev/null 2>&1; then
        echo "uvicorn server:app プロセスを検出。停止します。"
        pkill -f "uvicorn server:app" || true
    fi
    exit 0
fi

PID="$(cat "$PID_FILE")"

if ! kill -0 "$PID" 2>/dev/null; then
    echo "PID $PID は既に終了しています。"
    rm -f "$PID_FILE"
    exit 0
fi

echo "サーバを停止します (PID $PID)…"
# プロセスグループごと止めて子（infer.py 等）も確実に終了させる
kill -TERM "$PID" 2>/dev/null || true

# 最大 10 秒待つ
for _ in $(seq 1 10); do
    kill -0 "$PID" 2>/dev/null || break
    sleep 1
done

if kill -0 "$PID" 2>/dev/null; then
    echo "終了しないため強制終了します (SIGKILL)。"
    kill -KILL "$PID" 2>/dev/null || true
fi

rm -f "$PID_FILE"
echo "停止しました。"
