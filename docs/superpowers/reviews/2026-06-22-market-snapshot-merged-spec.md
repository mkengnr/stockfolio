# 시장별 종가·스냅샷 정합성 — 최종 합의 스펙 (Codex × Claude)

작성일: 2026-06-22
상태: **양측 수렴 완료**. 구현 계획(`/writing-plans`)의 입력으로 사용.
근거 문서: `2026-06-22-market-snapshot-evidence.md`, `*-codex-proposal.md`, `*-claude-proposal.md`, `*-codex-review-of-claude.md`(C1~C10), `*-claude-review-of-codex.md`, `*-codex-convergence-response.md`.
원칙: 코드 근거 기반, 추측 금지. 외부 거래소 달력 패키지 미도입. 마이그레이션에서 외부 API 호출 금지.

## 0. 합의 요약 (한 줄)

**"제공자 거래일(`price_date`)만 저장하고, 세션이 끝난 시장만 멱등 upsert로 확정하며, KRX/US를 분리 실행하고, 종가를 DB→Redis 동일 값으로 반영한다."** — 데이터 오염(R1·R2·R3)과 표면화 원인(R4 누락·R5 출처불일치·R6 전역기준)을 함께 제거.

## 1. 확정된 근본 원인 (심각도)

| ID | 원인 | 근거 | 심각도 |
| --- | --- | --- | --- |
| R1 | 종가를 `date.today()`(KST)로 저장(제공자 `price_date` 무시) → 미국 휴장·시차 시 잘못된 날짜 | `scheduler.py:45,72` | 치명 |
| R2 | 장중 세션을 종가로 확정(시작 백필 `end=today`가 장중 바 포함) | `scheduler._backfill_missing_snapshots`, `snapshot_service.py:80` | 치명 |
| R3 | 기존 날짜 미갱신 → 잘못된 장중/휴장 행 영구 잔존 | `snapshot_service.py:97` | 높음 |
| R4 | cron 미스파이어 방지 없음(grace 1초) → 1.968초 지연으로 15:35 종가 작업 누락 | `scheduler.py:86-96` | 높음 |
| R5 | 상단(Redis 300s TTL) vs 차트(PostgreSQL 스냅샷) 출처 불일치, 마감 후 재일치 장치 없음 | `price_cache.get_price` vs `lot_accounting.build_history` | 높음 |
| R6 | 대시보드 비교일 복구가 전역 최소 현재가 날짜를 모든 종목 기준으로 사용 | `portfolio.py:1520-1542` | 중간 |
| R7 | 확정/갱신 관측 부재(`created_at`만) | `models/snapshot.py:18` | 중간 |
| R8 | `total_value`가 비-lot(`h.quantity`) 기반 → 원장 재계산과 불일치(차트는 무시) | `scheduler.py:65` | 낮음~중간 |
| R9 | 종목 부분 실패가 티커·사유 없이 삼켜짐 | `scheduler.py:55-56` | 낮음 |
| R10 | KRX 현재가·종가가 동일 호출(장중/마감 의미 구분 없음) | `stock_fetcher._krx_latest_price` | 낮음 |

검증된 사실: APScheduler **3.11.2 = 인프로세스**(→ `max_instances=1`은 프로세스 내부 한정), `build_dashboard_response`가 summary·history에 **동일 `exchange_rate` 객체** 전달(→ 불일치 원인은 환율이 아니라 가격 스냅샷).

## 2. 보존할 강점

제공자 `price_date`가 실제 거래일(휴장 반영) 제공 · `_build_snapshot_values`의 원장 기반 수량·NaN 가드 · `build_history`의 가치불가 종목 일관 제외 · 유일키 `(holding_id, snapshot_date)` · 종목별 `price_date` 배선 존재 · `backfill_recent_comparison_snapshots`/`rebuild_holding_snapshots` 재사용.

## 3. 합의 아키텍처 (Codex 분리 스케줄 + Claude 확정 게이트)

### 3.1 시장 세션 정책 모듈 (신규 `backend/app/services/market_session.py`, 순수 함수)
- `safe_query_end(market, now) -> date`: 조회/백필 상한만 계산(저장일은 추정하지 않음). 미완료 당일 제외.
- `is_write_confirmed(market, price_date, now, *, close_overrides) -> bool`: 쓰기 게이트. `price_date < market_today` 이거나 (`price_date == market_today` 그리고 `now_market_local >= 확정 커트오프`)일 때만 True. 커트오프는 KRX 15:45·US 16:00 ET 기준이되 **`close_overrides`(연 1회 KRX 지연폐장)** 가 있으면 그 시각으로 대체.
- `zoneinfo`만 사용(외부 의존성 없음). 실제 세션일은 항상 제공자 바 `price_date`로 확정.

### 3.2 확정 단일 진입점 (`snapshot_service`)
- `finalize_market_snapshots(db, market, now)`:
  1. 해당 시장 활성 보유종목 조회 → 2. 종목별 최신가 직접 조회 → 3. `price is not None`·유한·양수·`price_date` 유효성 검증으로 **성공/실패 분리** → 4. **PostgreSQL `INSERT ... ON CONFLICT (holding_id, snapshot_date) DO UPDATE`** 멱등·원자 bulk upsert(키=`price_date`, **게이트 통과분만**) → 5. commit → 6. commit된 quote만 `price_cache.set_price`로 Redis 반영 → 7. 종목 실패는 구조화 로그.
  - `total_value`는 **원장 기반 해당일 수량 × price**로 산출(R8). (또는 컬럼 의미 폐기를 명시 — 결정: 재계산 채택.)
- `backfill_holding_snapshots`는 과거 누락만 담당하고 호출자가 `safe_query_end`를 반드시 전달(장중 오늘 제외).

### 3.3 캐시(`price_cache`)
- `set_price(ticker, PriceResult)` 공개 추가. **DB commit 성공 후에만** Redis set. Redis 실패는 롤백하지 않고 경고(다음 조회/TTL로 회복). DB가 진실원.

### 3.4 대시보드(`portfolio.py`)
- 비교 스냅샷 복구를 전역 `current_price_as_of` → **종목별 `quote.price_date`** 로 교체(R6).
- 시장 내 종목 기준일이 모두 같으면 단일 날짜, 다르면 `일부 종목 지연` 경고(+종목별 날짜). 상시 `from/to` 4필드는 미도입.
- summary와 마지막 history가 동일 `exchange_rate`를 쓴다는 회귀 테스트만 추가(구조 변경 없음).

### 3.5 표시(frontend)
- 장중: 상단 "장중 현재가(확정 전)" 라벨 + 차트는 직전 확정일까지(당일 미확정 점 미표시). 마감 후: 상단=차트 동일 종가.

## 4. 스케줄·시작·재시작·동시성

- **KRX finalize**: 월~금 15:45 KST. **US finalize**: 화~토 06:30 KST(미 금요일 종가 주말 공백 제거, 정규·조기폐장 모두 마감 이후).
- 각 cron: `misfire_grace_time=3600`, `coalesce=True`, `max_instances=1`.
- **시작 catch-up**: 부팅 시 과거 백필(`safe_query_end`로 상한) 후, 마감이 지난 시장만 `finalize_market_snapshots` 재실행(cron grace와 별개). 게이트가 장중 오늘 확정을 막음.
- **동시성**: DB `ON CONFLICT` upsert로 멱등·원자. 현재 launchd uvicorn **단일 worker 전제를 운영 문서에 명시**. 다중 worker 시 스케줄러 분리 또는 PostgreSQL advisory lock을 후속 조건으로.

## 5. DB/Redis 정합성 정책

1. 성공 quote 검증 → 2. PG bulk upsert + commit → 3. commit분만 Redis set → 4. Redis 실패는 경고만(DB 불변) → 5. TTL/다음 조회로 회복. 완료기준 1("마감 후 상단=차트")은 성공 경로에서 Redis가 동일 확정 종가를 담아 충족; Redis 실패 시 일시 불일치는 회복됨을 문서화.

## 6. KRX 특별 지연폐장 — 확정 결정

- **정책**: (b) **연 1회 수준 config override**(`market_close_overrides`, 예: 수능일 16:30) 채택. override가 있는 날은 `safe_query_end`·쓰기 게이트가 그 시각 전 당일 저장을 금지 → 완료기준 4("장중 종가 확정 금지")와 **충돌 없음**(폐장을 앞당기는 게 아니라 정상폐장 커트오프를 늦춤).
- **멱등 재확정은 방어층**으로만 유지(주 수단 아님). **override 누락**은 경고 로그 + 배포/운영 체크리스트로 드러냄(P2-15).
- 외부 거래소 달력 패키지는 미도입(과설계 제외).

## 7. 기존 데이터 복구 전략

- 별도 CLI `scripts/reconcile_daily_snapshots.py`(Alembic 아님, 외부 API 허용). **기본 dry-run**.
- 출력: 추가할 실제 거래일 / 갱신할 가격·평가금액 / 제공자 거래일에 없어 삭제할 잘못된 날짜 행 / 종목별 실패·총계.
- **최초 1회 전체 보유 기간 복구**(`first_buy_date`~최신 확정 세션) — `date.today()` 버그가 임의 과거일에 남겼을 수 있어 부분 정리로는 부족(완료기준 8). **종목별 순차·재시도·진행 체크포인트** 필수.
- 이후 **자동 시작 보정은 최근 14일**로 제한.
- **진실 판정 기준은 제공자 OHLC 비교**(`updated_at` 아님). 삭제는 제공자 바에 없는 파생 스냅샷만. 적용 전 DB 백업 + dry-run 결과 보관.

## 8. 파일별 변경 범위

| 파일 | 변경 |
| --- | --- |
| `backend/app/services/market_session.py` (신규) | `safe_query_end`, `is_write_confirmed`, `close_overrides` 처리 |
| `backend/app/services/snapshot_service.py` | `finalize_market_snapshots`(게이트+ON CONFLICT+원장 total_value+set_price 연동+구조화 로그); `backfill_holding_snapshots` 호출자가 `safe_query_end` 전달 |
| `backend/app/services/price_cache.py` | `set_price(ticker, PriceResult)` 공개 |
| `backend/app/tasks/scheduler.py` | KRX/US 분리 cron(grace/coalesce/max_instances), 시작 catch-up이 `finalize_market_snapshots` 사용, `date.today()` 저장 제거 |
| `backend/app/routers/portfolio.py` | 비교일 복구 종목별 `quote.price_date`; 시장 내 날짜 경고 |
| `backend/app/models/snapshot.py` | `updated_at`(`onupdate=func.now()`, `server_default`) |
| `backend/alembic/versions/*` (신규) | `daily_snapshots.updated_at` 추가(server_default), 외부 호출 없음 |
| `backend/app/config.py` | `market_close_overrides`(또는 동등), 스케줄 시각 설정화 |
| `backend/app/schemas/dashboard.py`, `frontend/lib/types.ts` | (필요 시) 지연 경고 필드 |
| `frontend/components/dashboard/DashboardOverview.tsx` | 장중 라벨, 시장별 날짜/경고, (차트) 당일 미확정 점 처리 |
| `scripts/reconcile_daily_snapshots.py` (신규) | dry-run/apply 복구 |
| `backend/tests/test_scheduler.py` (신규) + snapshot/dashboard/cache 테스트 | §9 |

## 9. TDD 테스트 매트릭스 (완료기준 매핑)

| 완료기준 | 테스트 | 단언 |
| --- | --- | --- |
| 5 (저장일=제공자일) | `test_snapshot::date_equals_provider_price_date` | upsert 키 = `pr.price_date` |
| 2 (장중 미확정) | `test_market_session::krx_intraday_before_1545_not_confirmed`; `test_snapshot::backfill_end_clamped_by_safe_query_end` | 15:44 False / 오늘 행 미생성 |
| 2 (마감 후 확정) | `test_market_session::krx_confirmed_after_1545`; `test_scheduler::start_after_close_finalizes_today` | 15:45 True / 오늘 1건 |
| 4 (휴장·DST) | `test_snapshot::us_holiday_stored_at_price_date_not_today`; `test_market_session::us_close_dst_and_early_close_safe_at_0630` | 6/18 저장·6/19 없음 / DST·조기폐장 안전 |
| 4 (KRX 지연폐장) | `test_market_session::krx_override_blocks_until_1630` | override일 16:29 False·16:30 True |
| 1 (US 금요일 적시) | `test_scheduler::us_friday_close_finalized_saturday_0630` | 토 06:30에 미 금요일 종가 확정 |
| 3 (지연·재시작 복구) | `test_scheduler::misfire_grace_coalesce_maxinstances`; `test_scheduler::start_catchup_recovers_missed_session` | grace>=3600·coalesce·max_instances=1 / 누락 복구 |
| 6 (멱등) | `test_snapshot::on_conflict_upsert_idempotent` | 재실행 행수 불변·값만 갱신 |
| 7 (부분 실패·로그) | `test_scheduler::ticker_failure_isolated_and_logged`; `test_snapshot::db_batch_failure_skips_redis` | 실패 티커 로그·나머지 저장 / DB 실패 시 Redis 미갱신 |
| 1 (상단=차트) | `test_dashboard::confirmed_close_db_equals_redis`; `test_dashboard::summary_and_last_history_same_exchange_rate` | DB close == Redis price / 동일 환율 |
| 8 (기존 복구) | `test_reconcile::dryrun_lists_no_write`; `::apply_fixes_holiday_and_intraday`; `::second_run_noop`; `::full_period_vs_14day_boundary` | dry-run 무쓰기·교정·재실행 0·범위 경계 |
| 10 (시장별 비교일·표시) | `test_dashboard::recovery_uses_per_holding_price_date`; `::same_market_diff_dates_warns_not_single`; `DashboardOverview::intraday_label_and_no_today_point` | 종목별 기준 / 경고 / 장중 라벨 |
| 9 (관측) | `test_snapshot::updated_at_changes_on_reconfirm`; `test_scheduler::override_missing_warns` | updated_at 갱신 / override 누락 경고 |
| R8 | `test_snapshot::total_value_uses_ledger_quantity` | total_value = 원장 수량 × price |
| 회귀 | 기존 `test_snapshot_service`/`test_dashboard_aggregate`/`test_portfolio_history` green | 단일 시장 동작 불변 |

## 10. 배포·복구·검증 순서

1. 전체 테스트 green(`pytest`, `npm test`, `npm run build`).
2. 운영 DB 백업.
3. 복구 CLI **dry-run** 및 결과 검토(전체 기간).
4. `./svc.sh deploy`(프론트 빌드 → `alembic upgrade`(updated_at) → 재시작). 재시작 시 시작 catch-up이 마지막 확정 세션 기록(장중이면 오늘 제외).
5. 복구 CLI `--apply` → 재실행 0건(멱등) 확인.
6. Redis 무효화 또는 종가 확정 1회 실행으로 상단=차트 일치 유도.
7. 검증(마감 후): 계정별 상단·차트·종목 합계 대조, 미국 휴장일(6/19) 행 부재·올바른 거래일 저장, 스케줄러 로그 misfire 없음·부분 실패 티커 경고, KRX override일 게이트 동작.
8. 다음 KRX·US 예약 작업 로그 확인.

## 11. 의도적으로 제외(과설계)

외부 거래소 달력 패키지 · 실시간 시세 제공자 교체 · 과거 환율 스냅샷 도입 · 스케줄러 별도 워커 분리(후속 조건으로만) · 관리자 수동복구 UI · 시장별 `current_from/to`·`comparison_from/to` 상시 4필드 · `confirmed_at` 별도 컬럼(게이트로 대체).

## 12. 남은 불확실성 (구현 전 확인)

1. **pykrx 장중 당일 OHLC 반환 형태** 실측(게이트는 안전하나 복구 분류 정확도에 영향).
2. **전체 기간 복구 비용**(제공자 호출량·레이트리밋·소요시간) 운영 데이터 규모로 산정, 체크포인트 단위 확정.
3. **프론트 마지막 history 점 표시**가 상단 평가금액과 **동일 환율·동일 수량 경로**를 쓰는지 회귀 테스트로 고정.
4. **KRX override 운영 프로세스**(연 1회 갱신·누락 감지)의 책임자·체크리스트 확정.

## 13. 우선순위 요구사항 (구현 계획 입력)

- **P0**: 저장=`price_date`(R1) · `safe_query_end`+쓰기 게이트(+override 입력)(R2,KRX) · KRX/US 분리 finalize·US 금요일 적시(R4,C1) · PG `ON CONFLICT` 멱등 upsert(C4) · DB→Redis 동일 종가(R5) · 비교일 종목별(R6) · KRX 지연폐장 override 설정.
- **P1**: 스케줄 하드닝+시작 catch-up(R4) · fetch 성공/실패 분리+구조화 로그(R9) · 전체기간 복구 CLI+자동14일(완료8) · `updated_at` 관측(R7) · `finalize` total_value 원장 수량(R8).
- **P2**: 시장 내 날짜 동일=단일/상이=경고(완료10) · 장중 라벨+차트 당일 점(완료10) · 동일 환율 회귀 테스트(완료1) · override 누락 관측 로그(완료9).

---

### 합의 상태
Codex와 Claude는 위 전 항목에 **합의**했다. 유일 미결이던 KRX 특별 지연폐장은 **config override(주) + 멱등 재확정(방어)** 으로 확정. 삭제 항목 없음. 본 문서는 검토·합의 산출물이며 구현은 시작하지 않았다.
