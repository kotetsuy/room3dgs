#!/usr/bin/env bash
# room3dgs — 起動スクリプト
#
# FastAPI サーバ（uvicorn）を 127.0.0.1:8000 でバックグラウンド起動する。
# 再構成本体（WorldMirror infer.py）は各リクエストごとに server 内から
# サブプロセス実行されるため、常駐させるのはこの 1 プロセスのみ。
#
# 使い方:  ./start_all.sh          # 既定 127.0.0.1:8000 で起動（nohup）
#          HOST=0.0.0.0 PORT=9000 ./start_all.sh
#
# ── STOP_GDM（GPUハングでログアウトしないための隔離実行・任意）────────────
#   gfx1151 は表示と計算が同一 iGPU のため、推論(infer.py)のGPUキューが
#   ハングして GPU リセットが走ると、デスクトップ(gnome-shell)まで道連れで
#   落ちてログアウトする。これを避けたい場合は GUI のターミナルから:
#       STOP_GDM=1 ./start_all.sh
#     → サーバを systemd 一時ユニット(room3dgs-headless)としてセッション外へ
#       切り離してから gdm を停止する。
#       HOST 未指定なら自動で 0.0.0.0 になり、別PCのブラウザから閲覧する。
#       gdm 停止前に 5 秒のカウントダウンがあり、Ctrl+C で中断できる
#       （中断してもサーバは動き続ける）。
#       GUI復帰: Ctrl+Alt+F3 → ログイン → sudo systemctl start gdm
#
#   ※テキストコンソール(TTY)からの HEADLESS/tmux 起動は一旦省略中
#     （まずは GUI 上で GPU エラーを観測する方針のため）。
set -euo pipefail

cd "$(dirname "$(readlink -f "$0")")"

HOST_EXPLICIT="${HOST+1}"   # HOST が明示指定されたか（GUI隔離起動の既定値切替に使う）
HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8000}"
STOP_GDM="${STOP_GDM:-0}"
UNIT="room3dgs-headless"    # GUI隔離起動時の systemd 一時ユニット名
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

# --- （任意）GUI(gdm)停止：GPUハングによるログアウト巻き添えを防ぐ ---
if [[ "$STOP_GDM" == "1" ]]; then
    if ! command -v systemctl >/dev/null 2>&1; then
        echo "エラー: systemctl が見つかりません。STOP_GDM は使えません。" >&2
        exit 1
    fi

    if [[ -n "${WAYLAND_DISPLAY:-}" || -n "${DISPLAY:-}" || "${XDG_SESSION_TYPE:-}" == wayland || "${XDG_SESSION_TYPE:-}" == x11 ]]; then
        # ── GUI セッション内からの実行 ──────────────────────────────
        # gdm を止めるとこの端末ごとセッションが閉じるため、先にサーバを
        # systemd の一時ユニット（セッション外・システム側）へ切り離す。
        # tmux はセッション内に居るとセッション終了に巻き込まれ得るので使わない。
        if [[ ! -x "$VENV_UVICORN" ]]; then
            echo "エラー: $VENV_UVICORN が見つかりません。" >&2
            exit 1
        fi
        # GUI が閉じるとローカルブラウザで見られないため、明示指定が無ければ外部公開にする
        if [[ -z "$HOST_EXPLICIT" ]]; then
            HOST="0.0.0.0"
        fi
        if systemctl is-active --quiet "$UNIT" 2>/dev/null; then
            echo "エラー: systemd ユニット '$UNIT' は既に稼働中です。停止: ./stop_all.sh" >&2
            exit 1
        fi

        echo "GUI からの隔離起動: サーバを systemd ユニット '$UNIT' に切り離します…"
        RUN_ARGS=(
            --collect --unit="$UNIT"
            -p User="$USER"
            -p WorkingDirectory="$PWD"
            -p "StandardOutput=append:$PWD/$LOG_FILE"
            -p "StandardError=append:$PWD/$LOG_FILE"
        )
        # ライブラリパスをシェルから引き継ぐ（systemd 配下では .profile が読まれない）
        [[ -n "${LD_LIBRARY_PATH:-}" ]] && RUN_ARGS+=(-p "Environment=LD_LIBRARY_PATH=$LD_LIBRARY_PATH")
        sudo systemd-run "${RUN_ARGS[@]}" \
            "$PWD/$VENV_UVICORN" server:app --host "$HOST" --port "$PORT"

        sleep 2
        if ! systemctl is-active --quiet "$UNIT"; then
            echo "起動に失敗しました。ログ: $LOG_FILE / journalctl -u $UNIT" >&2
            tail -n 20 "$LOG_FILE" >&2 || true
            exit 1
        fi
        systemctl show -p MainPID --value "$UNIT" > "$PID_FILE"

        echo "起動しました (PID $(cat "$PID_FILE"), unit $UNIT)  ログ: $LOG_FILE"
        echo "これからデスクトップ(gdm)を停止します。この端末や Chrome も閉じます。"
        echo "  閲覧    : 別PCで http://<このマシンのIP>:${PORT}/"
        echo "  GUI復帰 : Ctrl+Alt+F3 → ログイン → sudo systemctl start gdm（サーバは動き続ける）"
        echo "  停止    : ./stop_all.sh"
        echo -n "5秒後に gdm を停止します（Ctrl+C で中断。サーバは残ります）: "
        for i in 5 4 3 2 1; do echo -n "$i "; sleep 1; done
        echo
        sudo systemctl stop gdm
        exit 0
    fi

    # テキストコンソール(ttyN)/ssh からの STOP_GDM 起動は一旦省略中
    echo "エラー: STOP_GDM=1 は GUI セッション内のターミナルから実行してください。" >&2
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
