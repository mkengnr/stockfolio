# stockfolio

주식 투자 포트폴리오 관리 웹앱. 한국 주식(pykrx/KRX)과 해외 주식(yfinance)을 함께 관리합니다.

## 기술 스택

| 영역 | 기술 |
|------|------|
| Backend | Python 3.12, FastAPI, SQLAlchemy 2 (async), Alembic |
| DB | PostgreSQL 16 |
| Cache | Redis 7 (시세 캐싱, 5분 TTL) |
| 주식 데이터 | pykrx (KRX), yfinance (US) |
| Scheduler | APScheduler (일별 스냅샷) |
| Frontend | Next.js 14, TypeScript, Tailwind CSS, TradingView Lightweight Charts |
| Auth | 이메일 + 6자리 OTP, JWT (HttpOnly 쿠키) |

## 빠른 시작

```bash
# 1. 인프라 실행
docker compose up -d

# 2. 백엔드 환경 설정
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env   # 필요 시 수정

# 3. DB 마이그레이션
alembic upgrade head

# 4. 개발 서버 실행
uvicorn app.main:app --reload

# 5. 테스트
pytest
```

API 문서: http://localhost:8000/docs

## 프로젝트 구조

```
stockfolio/
├── backend/
│   ├── app/
│   │   ├── models/        # SQLAlchemy 모델
│   │   ├── schemas/       # Pydantic 스키마
│   │   ├── routers/       # FastAPI 라우터
│   │   ├── services/      # 비즈니스 로직 (stock_fetcher, auth, cache)
│   │   └── tasks/         # APScheduler 태스크
│   ├── tests/             # pytest 테스트
│   └── alembic/           # DB 마이그레이션
├── frontend/              # Next.js (별도 세션에서 구현)
├── docker-compose.yml
└── .env.example
```

## 종목 코드 규칙

- **한국 주식**: 6자리 숫자 (예: `005930` = 삼성전자, `000660` = SK하이닉스)
- **해외 주식**: 알파벳 티커 (예: `AAPL`, `TSLA`, `BRK.B`)

시장 자동 감지: 6자리 숫자 → KRX, 그 외 → US (yfinance)

## 주요 API

| 메서드 | 경로 | 설명 |
|--------|------|------|
| POST | `/api/auth/request-otp` | OTP 요청 |
| POST | `/api/auth/verify-otp` | OTP 검증 → JWT |
| GET | `/api/holdings` | 보유 종목 목록 (현재가 포함) |
| POST | `/api/holdings` | 종목 등록 |
| GET | `/api/tags` | 태그 목록 |
| POST | `/api/tags/{id}/share` | 공유 링크 생성 |
| GET | `/api/share/{token}` | 공개 포트폴리오 조회 |
