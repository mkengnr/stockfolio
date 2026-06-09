# 공유 페이지 대시보드 개선 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 그룹 공유 페이지에 안전한 공개 그룹 필터, 범위별 보유종목, 대시보드 통합 차트를 제공한다.

**Architecture:** 백엔드는 공유 범위에서만 대시보드 요약·이력·보유종목을 생성하고 공개용 임시 그룹 키로 연결한다. 프론트엔드는 공개 대시보드 계약을 메인 대시보드 차트 데이터 형태로 변환해 기존 통합 차트와 필터 동작을 재사용한다.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async, pytest, Next.js 14, TypeScript, Jest, TradingView Lightweight Charts

---

### Task 1: 공개 공유 대시보드 계약

**Files:**
- Modify: `backend/app/schemas/group.py`
- Modify: `backend/app/routers/groups.py`
- Modify: `backend/app/routers/portfolio.py`
- Test: `backend/tests/test_groups_api.py`

- [ ] 실제 통합 그룹 공유 범위를 재현하는 실패 테스트를 작성한다.
- [ ] 공개 그룹 키, 요약, 이력, 범위별 보유종목 스키마를 추가한다.
- [ ] 공유 범위 밖 그룹과 내부 UUID를 제외한 공개 대시보드 생성기를 구현한다.
- [ ] `cd backend && .venv/bin/python -m pytest tests/test_groups_api.py -q`로 검증한다.

### Task 2: 공유 페이지 필터와 통합 차트

**Files:**
- Modify: `frontend/lib/types.ts`
- Modify: `frontend/app/share/[token]/page.tsx`
- Modify: `frontend/__tests__/share/SharePage.test.tsx`

- [ ] 통합 그룹 공유 페이지의 필터·차트·보유종목 전환 실패 테스트를 작성한다.
- [ ] 공개 대시보드 타입과 메인 차트 입력 변환을 구현한다.
- [ ] 공유 페이지에 요약, 그룹 필터, 통합 차트, 범위별 보유종목을 연결한다.
- [ ] `cd frontend && npm test -- --runInBand __tests__/share/SharePage.test.tsx`로 검증한다.

### Task 3: 전체 검증과 운영 반영

**Files:**
- Modify only if verification reveals defects.

- [ ] 백엔드 전체 테스트를 실행한다.
- [ ] 프론트엔드 전체 테스트와 빌드를 실행한다.
- [ ] 프론트·백엔드 서비스를 재시작한다.
- [ ] 제공된 운영 공유 URL에서 전체 및 구성 그룹 필터와 차트를 시각 검증한다.

