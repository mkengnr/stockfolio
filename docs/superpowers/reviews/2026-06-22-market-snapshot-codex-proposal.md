# Codex 독립 개선안: 시장별 종가 확정과 스냅샷 정합성

## 판정

현재 문제는 단일 cron 지연 문제가 아니다. 다음 네 책임이 한 작업에 섞여 있어 오류가 연결된다.

1. 과거 거래일 백필
2. 당일 시장 종가 확정
3. 현재가 캐시 갱신
4. 대시보드 비교일 복구

해결책은 이 책임을 분리하고, 가격 제공자의 거래일을 유일한 저장 날짜로 삼는 것이다.

## 검토한 접근법

### A. 시장별 확정 작업과 시작 시 보정

- KRX와 US 작업을 서로 다른 안전 시각에 실행한다.
- 제공자의 실제 `price_date`로 upsert한다.
- 시작 시 마지막 완료 세션을 재검증한다.
- 확정 가격을 Redis와 DB에 함께 반영한다.

장점은 마감 직후 반영, 휴장일 안전성, 누락 자동 복구다. 작업 수가 늘지만 책임이 명확해진다.

### B. 10분 주기 범용 reconciler

- 모든 보유종목의 최신 가격일을 반복 확인한다.
- 새로운 완료 거래일이 보이면 DB와 Redis를 맞춘다.

구조는 단순하지만 외부 API 호출량이 크고 장중과 확정 가격을 구분하는 상태 관리가 필요하다.

### C. 다음 날 오전 단일 배치

- 미국장까지 끝난 후 전 시장을 한 번에 확정한다.

정합성은 높지만 KRX 차트 반영이 지나치게 늦다.

권장안은 A다.

## 권장 아키텍처

### 1. 시장 세션 정책 모듈

새 파일 `backend/app/services/market_session.py`가 다음 순수 함수를 제공한다.

- `safe_backfill_end(market, now_kst) -> date`
- `market_finalize_schedule(market) -> schedule metadata`
- `should_finalize_market(market, now_kst) -> bool`

KRX는 평일 15:45 이후 당일을 완료 가능일로 본다. US는 DST와 표준시 모두 안전하도록 화~토 06:30 KST 이후 가격 제공자의 최신 세션을 확정한다. 거래소 휴장 여부를 자체 달력으로 추측하지 않고 제공자의 실제 바 날짜로 최종 판정한다.

### 2. 과거 백필과 종가 확정 분리

`backfill_holding_snapshots`는 과거 누락일 추가만 담당한다. 호출자는 반드시 `safe_backfill_end`를 전달해 미완료 당일을 제외한다.

새 서비스 `finalize_market_snapshots`는 다음 순서로 동작한다.

1. 특정 시장의 활성 보유종목 조회
2. 각 종목의 최신 가격 직접 조회
3. `price is not None`, 유한수, 양수, `price_date` 유효성 검사
4. `(holding_id, price_date)` 기준 upsert
5. 동일 `PriceResult`를 Redis에 저장
6. 종목별 성공·실패 결과 수집
7. 성공 건 commit, 실패 건 구조화 로그 기록

저장 날짜에 `date.today()`를 사용하지 않는다.

### 3. 스케줄과 재시작 복구

- KRX: 월~금 15:45 KST
- US: 화~토 06:30 KST
- 각 cron: `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1`
- 시작 작업은 과거 백필 후, 마감 시각이 지난 시장에 한해 `finalize_market_snapshots`를 실행한다.
- upsert와 Redis set이 멱등적이므로 cron과 시작 복구가 겹쳐도 최종 값은 같다.

프로세스가 마감 시각 이후 시작되거나 한 시간 이상 중단된 경우도 복구해야 하므로, 시작 복구는 cron grace와 별개로 유지한다.

### 4. 캐시 일치

`price_cache.py`에 검증된 `PriceResult`를 저장하는 `set_price`를 추가한다. 종가 확정 작업은 직접 조회한 결과를 DB에 commit한 뒤 Redis에 쓴다.

DB commit 실패 시 Redis를 갱신하지 않는다. Redis 저장 실패 시 DB 종가를 롤백하지 않고 오류를 기록하며, 다음 대시보드 조회가 캐시 miss 또는 TTL 만료 후 복구하도록 한다.

### 5. 감사 가능성

`daily_snapshots`에 `updated_at`을 추가한다.

- `created_at`: 최초 행 생성
- `updated_at`: 마지막 가격 확정 또는 보정

마이그레이션은 `server_default=func.now()`에 해당하는 DB 기본값으로 기존 행을 backfill한다.

### 6. 기존 데이터 복구

Alembic에서는 네트워크를 호출하지 않는다. 별도 CLI `scripts/reconcile_daily_snapshots.py`를 추가한다.

CLI는 기본 dry-run이며 다음을 출력한다.

- 추가할 실제 거래일 행
- 가격·평가금액을 갱신할 행
- 제공자 거래일에 존재하지 않아 삭제할 잘못된 날짜 행
- 종목별 실패와 전체 건수

`--apply`에서만 변경한다. 적용 모드는 각 보유종목의 가격 이력을 다시 받아 지정 기간의 스냅샷을 거래 원장 기반 수량으로 재구축한다. 최초 운영 복구는 전체 보유 기간을 대상으로 하고, 이후 시작 시 자동 보정은 최근 14일만 대상으로 제한한다.

삭제는 조회 구간에서 제공자의 바 날짜가 아닌 파생 스냅샷만 대상으로 한다. 실행 전 DB 백업과 dry-run 결과 보관을 배포 체크리스트에 포함한다.

### 7. 대시보드 비교일 복구

`build_portfolio_dashboard_response`의 전역 `current_price_as_of` 기반 복구를 제거한다. 각 holding은 자신의 `quote.price_date`를 기준으로 이전 스냅샷을 확인하고 부족할 때만 해당 종목의 최근 구간을 백필한다.

시장 헤더는 같은 시장 안에서 비교일이 하나면 단일 날짜를 표시한다. 공급자 지연으로 종목별 날짜가 다르면 날짜 범위를 표시하거나 `일부 종목 지연` 경고를 함께 반환한다. 단일 최대 날짜로 모든 종목이 그 날짜를 사용한 것처럼 표시하지 않는다.

## 파일별 변경 범위

- 생성: `backend/app/services/market_session.py`
- 생성: `scripts/reconcile_daily_snapshots.py`
- 생성: `backend/tests/test_scheduler.py`
- 수정: `backend/app/tasks/scheduler.py`
- 수정: `backend/app/services/snapshot_service.py`
- 수정: `backend/app/services/price_cache.py`
- 수정: `backend/app/routers/portfolio.py`
- 수정: `backend/app/models/snapshot.py`
- 수정: `backend/app/schemas/dashboard.py`
- 수정: `frontend/lib/types.ts`
- 수정: `frontend/components/dashboard/DashboardOverview.tsx` 또는 기준일 표시 컴포넌트
- 생성: Alembic `daily_snapshots.updated_at` 마이그레이션
- 수정·추가: snapshot, dashboard, cache, scheduler 관련 테스트

## TDD 테스트 매트릭스

### 시장 세션

- KRX 마감 전에는 오늘을 백필하지 않는다.
- KRX 마감 후에는 제공자 `price_date=today`만 확정한다.
- US DST와 표준시 모두 06:30 KST 복구가 안전하다.
- 주말·휴장일에는 가짜 날짜 행을 만들지 않는다.

### 스케줄러

- 2초, 10분, 59분 지연은 실행된다.
- 중복 실행은 하나만 진행된다.
- 마감 후 시작하면 누락 세션을 복구한다.
- 마감 전 시작은 오늘 종가를 확정하지 않는다.

### 저장과 캐시

- snapshot 날짜는 `PriceResult.price_date`다.
- 동일 작업 재실행은 행 수를 늘리지 않고 가격만 갱신한다.
- DB commit 이후 Redis가 동일 가격·날짜를 가진다.
- Redis 실패가 DB 종가를 훼손하지 않는다.
- 일부 티커 실패 시 나머지 티커는 저장된다.

### 기존 데이터 복구

- 미국 휴장일에 잘못 붙은 행을 dry-run에서 검출한다.
- apply 후 실제 거래일 행만 남는다.
- 과거 거래일별 수량이 매수·매도 원장과 일치한다.
- 두 번째 apply 결과 변경 건수가 0이다.

### 대시보드

- 종목별 현재가 날짜로 직전 거래일을 선택한다.
- 혼합 시장 합계는 보유종목 변화 합과 같다.
- 같은 시장 안에서 날짜가 갈리면 단일 날짜로 오인 표시하지 않는다.
- 마감 확정 후 상단과 차트 마지막 평가금액이 일치한다.

## 배포 순서

1. 전체 테스트 통과
2. 운영 DB 백업
3. 복구 CLI dry-run 및 결과 검토
4. `./svc.sh deploy`
5. 복구 CLI `--apply`
6. 복구 CLI 재실행으로 변경 0건 확인
7. Redis 캐시 무효화 또는 종가 확정 작업 1회 실행
8. 계정별 상단·차트·종목 합계 대조
9. 다음 KRX 및 US 예약 작업 로그 확인

## 의도적으로 제외할 범위

- 거래소 달력 패키지 신규 도입
- 실시간 시세 제공자 교체
- 과거 환율 스냅샷 도입
- 스케줄러를 별도 워커 서비스로 분리
- 관리자 UI에서 수동 복구 기능 제공

이 항목은 현재 오류 해결에 필수적이지 않으며 별도 과제로 다룬다.

## 자체 비판

- `updated_at`과 복구 CLI는 최소 패치보다 범위가 크지만, 이번 오류의 탐지와 기존 데이터 정정에 필요하다.
- 최근 14일 자동 보정과 전체 기간 일회성 복구의 경계를 명확히 테스트해야 한다.
- Redis와 DB는 분산 트랜잭션이 아니므로 DB를 진실의 원천으로 두고 캐시 실패를 허용하는 정책을 문서화해야 한다.
- 미국 스케줄은 KST 06:30으로 단순화하지만 실제 저장 날짜는 반드시 제공자 날짜를 사용해야 한다.
