#!/bin/bash
# stockfolio 서비스 관리 스크립트
# 사용법: ./svc.sh [start|stop|restart|status]

PROJECT=/Users/Shared/workspace/stockfolio
BACKEND=$PROJECT/backend
FRONTEND=$PROJECT/frontend
LOGS=$PROJECT/logs
BREW=/opt/homebrew/bin/brew
NODE_BIN=/opt/homebrew/bin
USER_ID=$(id -u)
LAUNCH_AGENTS=$HOME/Library/LaunchAgents
BACKEND_LABEL=com.stockfolio.backend
FRONTEND_LABEL=com.stockfolio.frontend
BACKEND_PLIST=$PROJECT/scripts/launchd/$BACKEND_LABEL.plist
FRONTEND_PLIST=$PROJECT/scripts/launchd/$FRONTEND_LABEL.plist

mkdir -p "$LOGS"

install_agent() {
    LABEL=$1
    SOURCE=$2
    DEST=$LAUNCH_AGENTS/$LABEL.plist

    mkdir -p "$LAUNCH_AGENTS"
    cp "$SOURCE" "$DEST"
    launchctl bootout "gui/$USER_ID/$LABEL" >/dev/null 2>&1 || true
    launchctl bootstrap "gui/$USER_ID" "$DEST" >/dev/null 2>&1
    launchctl kickstart -k "gui/$USER_ID/$LABEL" >/dev/null 2>&1
}

uninstall_agent() {
    LABEL=$1
    launchctl bootout "gui/$USER_ID/$LABEL" >/dev/null 2>&1 || true
}

listening_pids() {
    lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null
}

start_services() {
    echo "=== stockfolio 시작 ==="

    # PostgreSQL
    echo -n "[1/4] PostgreSQL... "
    $BREW services start postgresql@16 >/dev/null 2>&1
    sleep 2
    if /opt/homebrew/bin/pg_isready -h 127.0.0.1 -q 2>/dev/null; then
        echo "✅ 실행 중"
    else
        echo "❌ 시작 실패 (로그: /opt/homebrew/var/log/postgresql@16.log)"
    fi

    # Redis
    echo -n "[2/4] Redis... "
    $BREW services start redis >/dev/null 2>&1
    sleep 1
    if /opt/homebrew/bin/redis-cli ping 2>/dev/null | grep -q PONG; then
        echo "✅ 실행 중"
    else
        echo "❌ 시작 실패"
    fi

    # Backend
    echo -n "[3/4] 백엔드 (포트 8000)... "
    if listening_pids 8000 >/dev/null 2>&1; then
        echo "⚠️  이미 실행 중 (건너뜀)"
    else
        install_agent "$BACKEND_LABEL" "$BACKEND_PLIST"
        sleep 3
        if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
            echo "✅ 실행 중"
        else
            echo "❌ 시작 실패 (로그: $LOGS/backend.log)"
        fi
    fi

    # Frontend
    echo -n "[4/4] 프론트엔드 (포트 3000)... "
    if listening_pids 3000 >/dev/null 2>&1; then
        echo "⚠️  이미 실행 중 (건너뜀)"
    else
        install_agent "$FRONTEND_LABEL" "$FRONTEND_PLIST"
        sleep 8
        CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null)
        if [ "$CODE" = "307" ] || [ "$CODE" = "200" ]; then
            echo "✅ 실행 중"
        else
            echo "❌ 시작 실패 (로그: $LOGS/frontend.log)"
        fi
    fi

    echo ""
    status_services
}

stop_services() {
    echo "=== stockfolio 중지 ==="

    echo -n "[1/4] 프론트엔드... "
    uninstall_agent "$FRONTEND_LABEL"
    PID=$(listening_pids 3000)
    if [ -n "$PID" ]; then
        kill "$PID" 2>/dev/null && echo "✅ 중지됨" || echo "❌ 실패"
    else
        echo "⚪ 이미 중지됨"
    fi

    echo -n "[2/4] 백엔드... "
    uninstall_agent "$BACKEND_LABEL"
    PID=$(listening_pids 8000)
    if [ -n "$PID" ]; then
        kill "$PID" 2>/dev/null && echo "✅ 중지됨" || echo "❌ 실패"
    else
        echo "⚪ 이미 중지됨"
    fi

    echo -n "[3/4] Redis... "
    $BREW services stop redis >/dev/null 2>&1 && echo "✅ 중지됨" || echo "❌ 실패"

    echo -n "[4/4] PostgreSQL... "
    $BREW services stop postgresql@16 >/dev/null 2>&1 && echo "✅ 중지됨" || echo "❌ 실패"
}

status_services() {
    echo "=== stockfolio 상태 ==="

    # PostgreSQL
    echo -n "  PostgreSQL : "
    if /opt/homebrew/bin/pg_isready -h 127.0.0.1 -q 2>/dev/null; then
        echo "🟢 실행 중 (:5432)"
    else
        echo "🔴 중지됨"
    fi

    # Redis
    echo -n "  Redis      : "
    if /opt/homebrew/bin/redis-cli ping 2>/dev/null | grep -q PONG; then
        echo "🟢 실행 중 (:6379)"
    else
        echo "🔴 중지됨"
    fi

    # Backend
    echo -n "  백엔드     : "
    if curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
        PID=$(listening_pids 8000 | head -1)
        echo "🟢 실행 중 (:8000, PID $PID)"
    else
        echo "🔴 중지됨"
    fi

    # Frontend
    echo -n "  프론트엔드 : "
    CODE=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000 2>/dev/null)
    if [ "$CODE" = "307" ] || [ "$CODE" = "200" ]; then
        PID=$(listening_pids 3000 | head -1)
        echo "🟢 실행 중 (:3000, PID $PID)"
    else
        echo "🔴 중지됨"
    fi

    echo ""
    echo "  앱 주소    : http://localhost:3000"
    echo "  외부 주소  : https://stock2.realchoi.com"
    echo "  API 문서   : http://localhost:8000/docs"
    echo "  로그 위치  : $LOGS/"
}

case "$1" in
    start)   start_services ;;
    stop)    stop_services ;;
    restart) stop_services; sleep 2; start_services ;;
    status)  status_services ;;
    *)
        echo "사용법: $0 {start|stop|restart|status}"
        echo ""
        echo "  start    - 모든 서비스 시작"
        echo "  stop     - 모든 서비스 중지"
        echo "  restart  - 재시작"
        echo "  status   - 현재 상태 확인"
        exit 1
        ;;
esac
