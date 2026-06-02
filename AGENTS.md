# Stockfolio

주식 투자 및 수익률 현황 관리 웹사이트

## 프로젝트 구조
- `backend/` — FastAPI + PostgreSQL + Redis
- `frontend/` — Next.js 14 (App Router) + TypeScript + Tailwind
- `scripts/` — 보조 스크립트 (codex_review.sh 등)

## 기술 스택
- **Backend**: Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic, Redis, pykrx, yfinance
- **Frontend**: Next.js 14, TypeScript, Tailwind CSS, SWR, TradingView Lightweight Charts
- **Auth**: Email + 6자리 OTP → JWT HttpOnly 쿠키 (30일 세션 옵션)
- **DB**: PostgreSQL 16 (brew), Redis 7 (brew)

## 개발 워크플로우 (필수)
1. **새 기능**: `/brainstorming` → `/writing-plans` 로 설계
2. **구현**: `/tdd` (red-green-refactor)
3. **리뷰**: `/codex:review` (표준) 또는 `/codex:adversarial-review` (도전적 모드)
4. **완료**: `/requesting-code-review` → 반영

## 실행
```bash
# DB / Cache (brew services)
brew services start postgresql@16
brew services start redis

# Backend (venv 안)
cd backend && .venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000

# Frontend
cd frontend && npm run dev

# Tests
cd backend && .venv/bin/python -m pytest tests/
cd frontend && npm test
```

## DB 설정
- 로컬 DB: `postgresql://stockfolio:stockfolio@127.0.0.1:5432/stockfolio`
- 마이그레이션: `cd backend && .venv/bin/alembic upgrade head`
- 새 마이그레이션: `.venv/bin/alembic revision --autogenerate -m "<msg>"`
  - NOT NULL 컬럼 추가 시 반드시 `server_default` 명시 (기존 행 backfill 위해)

## 보안 정책
- OTP: 6자리 숫자, bcrypt 해시, 10분 만료, **5회 실패 시 해당 OTP 잠금**
- JWT: HttpOnly 쿠키, jti hash를 sessions 테이블에 저장 (강제 로그아웃 지원)
- 모든 인증된 라우트는 소유자 검증 필수 (`*.user_id == current_user.id`)
- 공유 토큰: UUID v4, `share_requires_auth` 플래그로 인증 게이트 제어

## 주식 데이터
- 한국 (6자리 코드): pykrx
- 해외 (티커): yfinance
- 시장 자동 감지: `^\d{6}$` → KRX, 그 외 → US
- 향후: 토스증권 API로 교체 예정

## 배포
- Cloudflare Tunnel (설정 예정)
- GitHub: https://github.com/mkengnr/stockfolio

## 알려진 제약
- `next.config`는 `.mjs`만 사용 (Next.js 14.2.x TS config 미지원)
- `jest.config`는 `.js`만 사용 (ts-node 없는 환경)
- 테스트에서 Korean 라벨 입력은 `userEvent.type` 대신 `fireEvent.change`
- FastAPI 옵셔널 인증은 `Depends(get_current_user_optional)` 사용 (raw `User | None`은 query param으로 해석됨)
- 인증 실패 응답 직전에 명시적 `db.commit()` 필요 (HTTPException이 attempt_count 증가를 롤백시킴)
