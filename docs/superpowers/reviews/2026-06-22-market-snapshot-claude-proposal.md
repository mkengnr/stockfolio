# 시장별 종가·일별 스냅샷 오류 — 독립 개선안 (Claude)

작성일: 2026-06-22
근거: 공통 증거 문서 `docs/superpowers/reviews/2026-06-22-market-snapshot-evidence.md` + 저장소 읽기 전용 조사.
조사 범위(읽음): `tasks/scheduler.py`, `services/snapshot_service.py`, `services/price_cache.py`, `services/stock_fetcher.py`, `services/lot_accounting.py(build_history)`, `routers/portfolio.py(현재가 조회·복구·기준일)`, `models/snapshot.py`, `config.py`, `tests/test_snapshot_service.py`, `tests/test_dashboard_aggregate.py`, frontend `DashboardOverview.tsx`/테스트.

---

## 1. 근본 원인과 심각도

근거가 되는 코드 위치를 함께 표기한다.

| ID | 원인 | 근거 | 심각도 |
| --- | --- | --- | --- |
| R1 | **종가를 `date.today()`(KST)로 저장** — 제공자가 알려준 실제 거래일 `price_date`를 무시. 미국이 KST 오늘과 다른 거래일이면(휴장·시차) 잘못된 날짜에 기록. | `scheduler.py:45,62,72` (`today=date.today()`, upsert 키로 today 사용), `stock_fetcher.PriceResult.price_date`는 존재하지만 미사용 | **치명** |
| R2 | **장중 세션을 종가로 확정** — 시작 백필이 `end=date.today()`까지 요청하고, KRX 장중이면 제공자가 당일 장중 행을 반환. 그 장중가가 "당일 스냅샷=종가"로 굳어짐. (증거: 6/22 한국 스냅샷 10건 모두 10:08 KST 생성) | `scheduler._backfill_missing_snapshots`, `snapshot_service.backfill_holding_snapshots:80`(`end = end or date.today()`), `stock_fetcher._krx_latest_price`/`_krx_history`가 장중 행 포함 | **치명** |
| R3 | **기존 날짜는 건너뜀** — 백필이 이미 있는 날짜를 절대 갱신하지 않아, 잘못 적힌 장중/휴장 행이 영구히 남고 마감 종가로 교정되지 않음. | `snapshot_service.py:97`(`if value.snapshot_date in existing_dates: continue`) | **높음** |
| R4 | **스케줄 미스파이어 방지 없음** — cron에 `misfire_grace_time`/`coalesce`/`max_instances` 미설정. 기본 grace 1초 → 1.968초 지연으로 6/22 15:35 종가 작업이 통째로 누락. 장중 catch-up도 없음. | `scheduler.py:86-96`(옵션 없음) | **높음** |
| R5 | **상단(Redis)·차트(PostgreSQL) 출처 불일치** — 상단 평가금액은 Redis 현재가(TTL 300초), 차트 마지막 점은 `daily_snapshots` 종가. 마감 후 둘을 일치시키는 장치가 없음. (증거: 98,817,601 vs 99,254,849, 차이 437,248) | `portfolio._fetch_current_price_quotes`→`price_cache.get_price`(상단) vs `lot_accounting.build_history`가 스냅샷 종가 사용(차트) | **높음** |
| R6 | **복구 기준일이 전역 최소 날짜** — 비교 스냅샷 복구가 종목별 `quote.price_date`가 아니라 전 종목 최소 현재가 날짜(`current_price_as_of`)를 모든 종목의 기준으로 사용. 미국이 한국을 끌어내려 한국 종목 복구가 틀린 기준일로 동작. | `portfolio.py:1520-1542`(`current_price_as_of=_dashboard_current_price_as_of(min)`, `backfill_recent_comparison_snapshots(..., current_price_date=current_price_as_of)`) | **중간** |
| R7 | **확정/갱신 관측성 부재** — 스냅샷에 `created_at`만 있고 마지막 확정·갱신 시각이 없어 "장중 미확정 행"과 "마감 확정 행"을 구분·자가치유할 수 없음. | `models/snapshot.py:18`(created_at만) | **중간** |
| R8 | **`total_value`가 비-lot 수량 기반** — 종가 작업이 `h.quantity`(이동평균 비정규화 수량)로 total_value를 저장하나, 차트는 원장에서 수량을 재계산해 가격만 사용 → 저장된 total_value와 차트 표시가 불일치 가능(차트는 무시하므로 사실상 파생/잉여 컬럼). | `scheduler.py:65`(`h.quantity * close_price`) vs `lot_accounting.build_history`가 `_build_snapshot_values` 없이 close만 재결합 | **낮음** |
| R9 | **부분 실패 무관측** — 종가 작업의 종목 실패가 `except: continue`로 티커·사유 없이 삼켜짐. | `scheduler.py:55-56` | **낮음** |
| R10 | **KRX 현재가와 종가가 동일 호출** — `get_market_ohlcv_by_date` 마지막 행이 장중엔 현재가, 마감 후엔 종가로 의미가 달라지는데 코드가 구분하지 않음. | `stock_fetcher._krx_latest_price:142-144` | **낮음** |

핵심 한 줄: **"실제 거래일(price_date)을 무시하고 KST 오늘에, 세션이 끝나지도 않은 장중 가격을, 덮어쓰기 불가하게 저장"** 이 R1·R2·R3의 결합이 데이터 오염의 본질이고, R4(누락)·R5(출처 불일치)·R6(전역 기준)이 이를 표면화한다.

---

## 2. 현재 설계에서 잘된 부분 (보존 대상)

- 제공자 `PriceResult.price_date`가 **실제 거래일을 이미 정확히 반환**한다(휴장일은 제공자가 바를 주지 않으므로 별도 휴장 달력 없이도 신뢰 가능). 개선의 1차 진실원은 이미 존재한다.
- `_build_snapshot_values`가 **원장 기반 보유수량으로 재계산**하고 NaN/비유한/0 이하 종가 바를 건너뛴다 → 파생 가치가 견고. (`snapshot_service.py:32-68`)
- `build_history`가 **가치 불가 종목을 value·cost 양쪽에서 제외**하고, 통화 전체가 평가 불가일 때만 null 처리 → 혼합 시장에서 한 종목 결측이 시리즈 전체를 망가뜨리지 않음. (`lot_accounting.build_history`)
- `daily_snapshots`의 **유일 키 `(holding_id, snapshot_date)`** 가 멱등 upsert의 자연 키로 적합.
- 종목별 `price_date`가 이미 `_fetch_current_price_quotes`까지 배선되어 있고, 시장별 전일대비/기준일(`price_dates_by_market`)도 이미 도입됨 → 복구 기준일을 종목별로 바꾸는 데 추가 배선 비용이 작다.
- `backfill_recent_comparison_snapshots`, `rebuild_holding_snapshots`, `get_price_history`/`get_price_on_date` 등 **재사용 가능한 복구·조회 함수와 테스트**가 이미 존재.
- `get_current_price`의 NaN/Inf → `price=None` 가드.

---

## 3. 해결 접근법 (최소 2개)

### 접근 A — "price_date 저장 + 세션 확정 게이트" (최소 변경)

핵심 규칙 2가지만 도입한다.

1. **저장 키를 `price_date`로** 바꾼다(R1). `date.today()`로 저장하지 않는다.
2. **세션 확정 게이트**: 시장 M·날짜 D의 가격은 다음일 때만 "확정 종가"로 본다.
   - `price_date < 그 시장 타임존의 오늘` (과거 세션 → 항상 확정), 또는
   - `price_date == 오늘 AND now_in_market_tz >= 그 날 정규장 마감 시각`.
   - 그렇지 않으면 **장중 → 스냅샷에 쓰지 않는다**(R2). 백필 `end`도 "마지막 확정 거래일"로 클램프.
3. 게이트를 통과한 행은 **멱등 upsert로 덮어쓰기 허용**(R3) → 마감 작업이 같은 날 잘못된 행을 교정.
4. 스케줄 하드닝: `misfire_grace_time`, `coalesce=True`, `max_instances=1`(R4).
5. 복구 기준일을 **종목별 `quote.price_date`** 로 교체(R6).

장점: 변경 표면이 작고 기존 테스트 영향 최소. 휴장/DST는 제공자 price_date가 자동 처리. 단점: 마감 직후 상단(Redis)·차트가 "동일 종가"가 되려면 Redis 갱신 타이밍에 의존(아래 §8에서 보강).

### 접근 B — "확정 플래그 + Redis 공동 확정 + 자가치유 카탈로그" (관측성·정합성 강화)

접근 A에 더해:

- `daily_snapshots`에 `updated_at`(필수)과 `confirmed_at`(선택) 추가(R7) → "장중 미확정/마감 확정"을 데이터로 구분, 관측·자가치유 가능.
- **종가 확정 작업이 Redis 현재가도 같은 값으로 set**(공개 `set_price` 추가) → 마감 후 상단(Redis)·차트(스냅샷)가 **동일 종가**를 사용(R5, 완료기준 1 직접 충족).
- 시작 시 **마지막 완료 세션 재확정 catch-up**: 누락이면 생성, 미확정(또는 마감 전 created)이면 확정 종가로 재기록.

장점: 완료기준 1·9를 데이터 차원에서 강하게 보장, 자가치유. 단점: 마이그레이션 1건(서버 디폴트 필요), 변경 표면이 A보다 큼.

### 접근 C — 외부 마켓 캘린더 도입(pandas-market-calendars 등)

명시적 휴장/반장/DST 달력으로 거래일을 직접 판정. → **과설계로 제외**(§13). 제공자 price_date가 이미 휴장을 반영하므로 추가 의존성·동기화 비용 대비 이득이 작다. 단, 마감 시각 판정(KRX 15:30 KST / US 16:00 ET)만 표준 라이브러리 `zoneinfo`로 처리한다.

---

## 4. 접근법별 장단점·운영 위험

| 접근 | 장점 | 단점 | 운영 위험 | 완료기준 충족도 |
| --- | --- | --- | --- | --- |
| A | 변경 작음, 빠른 적용, 테스트 영향 최소 | 마감 직후 상단·차트 일치가 Redis 타이밍 의존, 미확정 식별 불가 | 낮음(스키마 무변경) | 1을 "거의" 충족(타이밍 의존), 2·3·4·5·6·7 충족 |
| B | 완료기준 1·9 강하게 보장, 자가치유·관측성 | 마이그레이션 1건, 코드 표면 증가 | 중간(서버 디폴트·백필 필요), 멱등 upsert로 완화 | 전부 충족 |
| C | 이론적으로 가장 정밀한 거래일 판정 | 외부 의존성·달력 동기화·테스트 비용 | 중간~높음 | 제공자 대비 한계이익 적음 |

운영 위험 공통 메모: Alembic 마이그레이션에서 **외부 가격 API 호출 금지**(증거 §데이터 모델). 기존 데이터 교정은 마이그레이션이 아니라 별도 dry-run 스크립트로 수행한다.

---

## 5. 최종 권장안

**접근 B(= A 전체 + Redis 공동 확정 + `updated_at` + 시작 재확정)를 권장**한다. 단 `confirmed_at` 별도 컬럼은 선택으로 두고, 1차 구현은 `updated_at` 하나로 시작한다(미확정 식별은 "장중엔 아예 쓰지 않는다"는 게이트로 대체 가능하므로 `confirmed` 플래그 없이도 정합성은 보장된다 — §13 참고).

권장 구성요소:
1. `market_session` 유틸(신규): 시장별 마감 시각·확정 판정. `zoneinfo` 사용, 외부 의존성 없음.
2. 스냅샷 쓰기 단일 진입점 `record_confirmed_snapshot`(신규, snapshot_service): price_date 키 + 세션 확정 게이트 + 멱등 upsert + `updated_at` 갱신. 스케줄러/백필/복구가 모두 이 함수만 사용.
3. 종가 작업이 확정 종가를 **DB 스냅샷 + Redis** 양쪽에 기록(`price_cache.set_price` 신규).
4. 스케줄 하드닝(misfire_grace_time/coalesce/max_instances).
5. 시작 catch-up: 마지막 완료 세션까지 누락·미확정 재확정(장중 오늘 제외).
6. 대시보드 복구 기준일을 종목별 `price_date`로 교체.
7. 부분 실패 로깅 + 관측 필드(`updated_at`) 노출.
8. 기존 오염 데이터 dry-run 복구 스크립트.

---

## 6. 시장별 종가 확정 데이터 흐름

용어: `now`는 UTC, 시장 타임존은 KRX=`Asia/Seoul`(마감 15:30), US=`America/New_York`(마감 16:00, DST 자동).

```
get_current_price(ticker) → PriceResult(price, price_date, market)
        │
        ▼
is_confirmed_close(market, price_date, now):
   market_today = now.astimezone(market_tz).date()
   if price_date  < market_today: return True           # 과거 세션 = 확정
   if price_date == market_today:
       return now_market_local_time >= market_close_time # 마감 지났으면 확정
   return False                                          # 미래/이상치 = 미확정
        │ 확정만 통과
        ▼
record_confirmed_snapshot(db, holding, price=price, snapshot_date=price_date):
   upsert (holding_id, price_date):
     close_price = price (확정 종가)
     total_value = (선택) 원장 재계산 수량 × price   # R8 정합화, 또는 컬럼 deprecate
     updated_at  = now
   # 멱등: 같은 입력 재실행은 동일 결과
        │
        ├─▶ DB daily_snapshots (차트 출처)
        └─▶ price_cache.set_price(ticker, price, price_date)  # Redis (상단 출처) 동일 값
```

- **장중**(미확정): 스냅샷에 오늘 행을 쓰지 않는다. 차트의 마지막 점은 "마지막 확정 거래일"에 멈춘다. 상단은 라이브 Redis 현재가를 그대로 보여주되 화면에 "장중 현재가"임을 표기(§8, §10).
- **마감 후**: 종가 작업이 DB·Redis에 동일 확정 종가를 기록 → 상단=차트 마지막이 **동일 가격**(완료기준 1). 환율은 §8 정책으로 동일 기준 적용.

미국 사례(6/19 NYSE 휴장): 제공자 price_date=6/18 → 게이트는 6/18에 저장(6/19 아님). 6/19 행을 만들지 않으므로 R1 해결.

---

## 7. 시작·재시작·스케줄 지연 복구 흐름

```
앱 시작(lifespan):
  for holding in active:
    last_session = 최근 "확정" 거래일 (제공자 price_date 또는 시장 마감 판정으로 산출)
    record_confirmed_snapshot 으로 [first_buy_date .. last_session] 누락분 backfill
      - end 를 last_session 으로 클램프 → 장중 오늘 미포함(완료기준 2)
      - 기존 행이 있어도 'updated_at 없음 또는 장중 생성 의심'이면 재확정(R3 교정)
스케줄(KST 15:35 mon-fri):
  CronTrigger(..., misfire_grace_time=3600, coalesce=True, max_instances=1)
    - 수초~수분 지연도 실행(완료기준 3, R4)
    - 중복/겹침 방지(max_instances=1), 누락 합치기(coalesce)
재시작 타이밍:
  - 장중 재시작: 게이트가 오늘 종가 확정을 막음(완료기준 2)
  - 마감 후 재시작: 시작 catch-up이 그 날 확정 종가를 기록(완료기준 3)
멱등성:
  - 모든 쓰기는 upsert (ON CONFLICT (holding_id, snapshot_date)) → 재실행/중복 프로세스 동일 결과(완료기준 6)
```

스케줄러가 프로세스 내(in-process)라 15:35에 프로세스가 죽어 있으면 그날 cron은 발화하지 않는다 → **시작 catch-up이 안전망**이다(둘은 같은 `record_confirmed_snapshot`을 사용해 일관).

---

## 8. DB와 Redis 정합성 정책

- **확정 시점 공동 기록**: 종가 확정 작업은 DB 스냅샷과 Redis 현재가를 **동일 확정 종가**로 같이 set. 마감 후 상단(Redis)·차트(DB)가 같은 숫자(완료기준 1).
- **TTL과 마감**: Redis TTL 300초는 유지하되, 마감 후 첫 라이브 조회 또는 종가 작업의 set으로 Redis가 종가를 담게 되므로 상단도 종가로 수렴. (장중엔 TTL대로 라이브 현재가)
- **환율 정합**: 상단·차트가 USD→KRW 환산에 **동일 환율 스냅샷**을 쓰도록, 대시보드 응답이 사용한 환율을 한 곳에서 산출해 상단·차트 표시에 공통 적용(완료기준 1의 "환율 기준" 부분). KRX(KRW) 종목은 환율 무관하므로 종가만 같으면 일치.
- **출처 단일화 옵션(선택)**: 마감 후에는 상단도 "당일 확정 스냅샷"을 우선 사용하도록 하면 출처가 하나로 합쳐져 불일치 가능성을 구조적으로 제거. 단, 장중엔 라이브가 필요하므로 "마감 여부"에 따라 출처를 전환. (구현 복잡도 ↑ → 1차는 §8 첫 항목의 공동 기록으로 충분)
- **장중 표기**: 장중에는 화면에 "장중 현재가(확정 전)"임을 명시하고 차트는 직전 확정일까지만 그려, 상단≠차트가 "버그"가 아니라 "장중"임을 사용자가 이해하도록 함(완료기준 10).

---

## 9. 기존 데이터 복구 전략

마이그레이션이 아닌 **관리 스크립트**(예: `scripts/recover_market_snapshots.py`)로 수행. 외부 API 호출 허용(마이그레이션 금지 제약 회피).

절차(반드시 dry-run 우선):
1. 대상: 모든 활성 holding의 최근 N영업일(예 30일) 스냅샷.
2. 각 행을 제공자 `get_price_history`의 실제 거래일·종가와 대조:
   - **휴장일 행**(제공자에 해당 날짜 바 없음): 잘못된 날짜 → 삭제 또는 올바른 price_date로 이동(같은 가격이 직전 거래일에 이미 있으면 삭제).
   - **장중 의심 행**(`created_at`이 그 시장 마감 시각 이전 & 종가와 불일치): 확정 종가로 재기록.
   - **누락 확정일**: 생성.
3. dry-run은 변경 예정 목록(holding, date, old→new)을 출력만. `--apply`로 트랜잭션 적용.
4. 멱등: 재실행 시 추가 변경 0건(검증 항목).
5. 스크립트 핵심 로직은 순수 함수로 분리해 단위 테스트(§11)로 검증(`test_group_migration.py` 패턴 차용).

US 6/19, KRX 6/22 장중 오염 행이 1차 복구 대상.

---

## 10. 파일별 변경 범위

| 파일 | 변경 | 비고 |
| --- | --- | --- |
| `backend/app/services/market_session.py` (신규) | `market_close_dt()`, `is_confirmed_close(market, price_date, now)`, `last_confirmed_session(market, now)` | `zoneinfo`만 사용, 외부 의존성 없음 |
| `backend/app/services/snapshot_service.py` | `record_confirmed_snapshot()` 신규(게이트+멱등 upsert+updated_at); `backfill_holding_snapshots`가 `end`를 마지막 확정일로 클램프하고 미확정 행 교정 옵션 | 기존 `_build_snapshot_values` 재사용 |
| `backend/app/services/price_cache.py` | `set_price(ticker, price, price_date)` 공개 함수 추가 | 종가 작업이 Redis 공동 기록 |
| `backend/app/tasks/scheduler.py` | `_save_daily_snapshots`가 `price_date`로 저장+게이트+`record_confirmed_snapshot` 사용+Redis set+티커 실패 로깅; cron에 misfire_grace_time/coalesce/max_instances; 시작 catch-up이 마지막 확정 세션까지 | `date.today()` 저장 제거 |
| `backend/app/routers/portfolio.py` | 비교 스냅샷 복구가 `current_price_as_of`(전역 min) 대신 **종목별 `quote.price_date`** 사용 | `build_portfolio_dashboard_response:1520-1542` |
| `backend/app/models/snapshot.py` | `updated_at` 컬럼 추가(`onupdate=func.now()`, `server_default`) | 관측성·자가치유 |
| `backend/alembic/versions/*` (신규) | `daily_snapshots.updated_at` 추가, `server_default=func.now()` | 외부 API 호출 없음 |
| `backend/app/main.py` (lifespan) | 시작 catch-up 호출 경로 점검(이미 `_backfill_missing_snapshots` 존재) | 동작만 교체 |
| `backend/app/config.py` | (선택) `snapshot_misfire_grace_seconds` 등 스케줄 옵션 설정화 | 기본값 보수적 |
| `scripts/recover_market_snapshots.py` (신규) | 기존 오염 데이터 dry-run/apply 복구 | §9 |
| `frontend/components/dashboard/DashboardOverview.tsx` | 장중/확정 표기, `updated_at` 등 "마지막 확정 시각" 노출(응답 필드 추가 시) | 표시 정확성(완료기준 10) |
| 프론트 차트 표시 | 장중에는 오늘 미확정 점을 그리지 않거나 "장중" 라벨 | 상단≠차트가 장중임을 설명 |

---

## 11. 구체적 TDD 테스트 매트릭스

각 완료기준에 대응하는 테스트를 명시(backend는 pytest, 제공자/Redis/DB는 기존 패턴대로 mock/SimpleNamespace).

| # | 완료기준 | 테스트 (파일::이름) | 핵심 단언 |
| --- | --- | --- | --- |
| T1 | 마감 후 상단=차트 동일 가격·환율 | `test_snapshot_consistency::test_confirmed_close_writes_db_and_redis_same_value` | 종가 작업 후 `daily_snapshots.close_price == price_cache.get_price().price` |
| T2 | 장중 시작이 당일 종가 확정 안 함 | `test_snapshot_service::test_record_skips_intraday_today` | KRX `now=10:08`, price_date=오늘 → 쓰기 0건 |
| T3 | 마감 후 시작은 당일 확정 | `test_snapshot_service::test_record_confirms_after_close` | KRX `now=15:35` → 오늘 행 1건 upsert |
| T4 | 스케줄 지연 자동 복구 | `test_scheduler::test_cron_has_misfire_grace_and_coalesce` | add_job 인자에 `misfire_grace_time>=수분`, `coalesce=True`, `max_instances=1` |
| T5 | 미국 휴장일 잘못된 날짜 미생성 | `test_snapshot_service::test_us_holiday_stored_at_price_date_not_today` | price_date=6/18, today(KST)=6/19 → 6/18에 저장, 6/19 행 없음 |
| T6 | DST 마감 판정 | `test_market_session::test_us_close_respects_dst` | 3월/11월 경계에서 ET 16:00 == 올바른 UTC |
| T7 | KRX 마감 판정 | `test_market_session::test_krx_close_1530_kst` | 15:29 미확정 / 15:30 확정 |
| T8 | price_date == 저장일 | `test_snapshot_service::test_snapshot_date_equals_provider_price_date` | upsert 키가 `pr.price_date` |
| T9 | 멱등 재실행 | `test_snapshot_service::test_record_is_idempotent` | 동일 입력 2회 → 행 수·값 불변, 두 번째 added=0 |
| T10 | 부분 실패 격리·로깅 | `test_scheduler::test_one_ticker_failure_does_not_block_others` | A실패·B성공 → B 기록 1건, 경고 로그에 A 티커 |
| T11 | 기존 데이터 dry-run 복구 | `test_recover_snapshots::test_dryrun_lists_changes_without_writing` / `::test_apply_fixes_holiday_and_intraday_rows` / `::test_second_run_is_noop` | dry-run 쓰기 0, apply 교정, 재실행 0건 |
| T12 | 시장별 전일대비·기준일 정확 | `test_dashboard_aggregate::test_recovery_uses_per_holding_price_date` (신규) + 기존 `test_dashboard_*per_market*` | 복구 기준일이 종목별 `quote.price_date`, 전역 min 미사용 |
| T13 | 기존 회귀 | 기존 `test_snapshot_service.py`, `test_dashboard_aggregate.py`, `test_portfolio_history.py` 전부 green | 단일 시장 동작 불변 |
| T14 | 관측성 | `test_snapshot_service::test_updated_at_changes_on_reconfirm` | 재확정 시 `updated_at` 갱신 |
| T15 | 백필 end 클램프 | `test_snapshot_service::test_backfill_end_clamped_to_last_confirmed_session` | 장중 호출 시 오늘 행 미생성 |

프론트:
| T16 | 장중/확정 표기 | `DashboardOverview.test::shows_intraday_label_during_session` | 장중이면 "장중" 라벨, 마감 후엔 확정 기준일 표기 |

---

## 12. 배포·복구·검증 순서

1. **코드 머지 전 검증**: 신규/회귀 테스트 전부 green(`pytest tests/`, `npm test`), `npm run build`.
2. **마이그레이션**: `daily_snapshots.updated_at` 추가(`server_default=func.now()`), `alembic upgrade head`. 외부 API 호출 없음 확인.
3. **배포**: `./svc.sh deploy`(프론트 빌드→alembic→재시작). 재시작 시 시작 catch-up이 마지막 확정 세션을 기록(장중이면 오늘 제외).
4. **기존 데이터 복구**: `scripts/recover_market_snapshots.py --dry-run`으로 변경 목록 확인 → 검토 후 `--apply`. 이후 `--dry-run` 재실행이 0건인지 확인(멱등).
5. **검증(마감 후 KST 15:35 이후)**:
   - 상단 평가금액 == 차트 마지막 평가금액(동일 가격·환율).
   - 6/19 같은 미국 휴장일 행이 없고, 미국 종가가 올바른 거래일에 저장.
   - 스케줄러 로그에 misfire 없이 실행, 부분 실패 시 티커 경고.
6. **롤백**: 마이그레이션은 additive(컬럼 추가)라 다운 리스크 낮음. 코드 롤백 시에도 데이터 손상 없음(복구는 별 스크립트).

---

## 13. 과설계 가능성 → 제외할 항목

- **외부 마켓 캘린더(pandas-market-calendars 등) 도입**: 제공자 price_date가 휴장을 이미 반영하므로 제외. 마감 시각만 `zoneinfo`로 처리.
- **`confirmed_at` 별도 컬럼 + 명시적 confirmed 플래그**: "장중엔 아예 쓰지 않는다"는 게이트로 모든 기록 행이 확정이 되므로 1차에선 불필요. 관측성은 `updated_at`로 충분. (재확정 추적이 더 필요해지면 그때 추가)
- **종가 전용 분리 테이블/이벤트 소싱**: 현 `daily_snapshots` upsert로 충분. 신규 테이블 불필요.
- **실시간(분봉) 스트리밍·웹소켓 가격**: 범위 밖.
- **`total_value` 컬럼 전면 재설계**: 차트가 재계산하므로, 정합만 맞추거나(원장 수량 사용) 컬럼 deprecate 메모만 남기고 큰 리팩토링은 보류.
- **상단/차트 출처 완전 단일화(마감 여부에 따른 출처 전환)**: 정합성은 §8 "공동 기록"으로 달성 가능하므로 1차 제외(선택 항목으로만 명시).

---

## 14. 아직 불확실하거나 추가 확인이 필요한 부분

1. **pykrx 장중 동작**: `get_market_ohlcv_by_date`가 장중에 "오늘" 행을 어떤 값(현재가/직전 종가/공백)으로 반환하는지 실측 필요. 게이트 설계는 "오늘=미확정"으로 안전하게 막으므로 정확값과 무관하게 안전하나, 6/22 10:08 행이 정확히 어느 값이었는지(현재가 vs 직전 종가)는 복구 분류에 영향.
2. **KRX 반장(조기 마감)일**: 명절 전후 12:30 조기 마감 등. 1차는 정규 15:30 기준; 제공자 price_date가 그날 바를 주면 과거 세션 규칙으로 확정되므로 큰 문제 없을 것으로 보이나 검증 필요.
3. **차트 표시값의 환율 적용 지점**: 차트 "마지막 평가금액"이 KRW 단일 통화인지, USD 환산을 포함하는지(그리고 어떤 환율 시점인지)를 프론트 표시 코드에서 확정해야 완료기준 1의 "환율 기준 일치"를 정확히 충족. (이번 조사에서 상단·차트의 환율 적용 동일성은 미확정)
4. **Redis `set_price`와 라이브 조회 경쟁**: 마감 직후 종가 set과 사용자 요청의 라이브 get_price가 경쟁할 때 TTL/덮어쓰기 순서. upsert·set 멱등이라 값은 같지만 타이밍 라벨링은 점검 필요.
5. **시작 catch-up 비용**: 보유 종목·기간이 많을 때 부팅 시 제공자 호출 폭. 동시성·레이트리밋(현재 `asyncio.gather`)과 부팅 지연 영향 측정 필요.
6. **마지막 확정 세션 산출 방식**: 시장 마감 판정으로 계산할지, "제공자 최신 price_date"를 신뢰할지. 둘이 어긋나는 엣지(데이터 지연)에서의 우선순위 규칙 확정 필요.

---

## 자체검토 결과

- **TBD/TODO/모호 표현**: 본문에 TBD/TODO 없음. 불확실 항목은 §14에 "추가 확인 필요"로 분리 명시(완료 기준의 모호함이 아니라 실측 대상).
- **함수·파일·데이터 흐름 일관성**: `record_confirmed_snapshot`(snapshot_service), `is_confirmed_close`/`last_confirmed_session`(market_session), `set_price`(price_cache), 복구 기준일=종목별 `price_date`(portfolio.py)가 §6·§7·§10·§11에서 동일 명칭·역할로 일관 사용됨. 모순 없음.
- **완료기준↔테스트 매핑**: 완료기준 1→T1/T16, 2→T2/T15, 3→T3/T4, 4→T5/T6/T7, 5→T8, 6→T9, 7→T10, 8→T11, 9→T14, 10→T12/T16. 전 기준에 대응 테스트 존재.
- **과설계 점검**: 외부 캘린더·confirmed 컬럼·신규 테이블·출처 완전단일화를 §13에서 명시적으로 제외. 1차 구현은 마이그레이션 1건(updated_at)·신규 유틸 1개·스크립트 1개로 한정.
- 자체검토에서 발견해 반영한 사항: (a) `confirmed_at`을 필수에서 선택으로 강등하고 게이트로 대체(과설계 축소), (b) 완료기준 1의 "환율 기준" 충족을 위해 §8에 환율 정합 항목과 §14에 환율 적용 지점 불확실성을 추가, (c) 시작 catch-up과 cron이 동일 `record_confirmed_snapshot`을 공유하도록 §7에서 일관화.

(구현은 시작하지 않음. 본 문서는 검토·제안 전용.)
