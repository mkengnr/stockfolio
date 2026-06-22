# Codex·Claude 개선안 비교 초안

이 문서는 Claude의 Codex 교차검토 전 초안이다. 최종 통합안이 아니다.

| 쟁점 | Codex 독립안 | Claude 독립안 | 초안 판정 |
| --- | --- | --- | --- |
| 실제 저장 날짜 | `PriceResult.price_date` | `PriceResult.price_date` | 합의, 채택 |
| 장중 당일 행 | safe end로 제외 | 세션 확정 게이트로 제외 | 게이트 + safe end 결합 |
| KRX/US 스케줄 | 15:45 / 화~토 06:30 분리 | 단일 15:35 설명이 남음 | Codex 방향 채택 |
| 미스파이어 | grace 3600, coalesce, max_instances | 동일 | 합의, 채택 |
| 시작 복구 | 마감 후 시장별 재확정 | 마지막 완료 세션 catch-up | 합의, 단 날짜 추측 금지 |
| DB 쓰기 | 멱등 upsert | 멱등 upsert | PostgreSQL ON CONFLICT 명시 |
| Redis 순서 | DB commit 후 Redis | 공동 기록, 순서 불명확 | Codex 방향 채택 |
| 기존 데이터 | 최초 전체 기간, 이후 최근 14일 | 최근 N일 예시 30일 | 최초 전체 기간 채택 |
| 관측성 | `updated_at` | `updated_at` | 합의, 감사 용도로만 사용 |
| 비교일 복구 | 종목별 quote date | 동일 | 합의, 채택 |
| 시장 내 날짜 불일치 | 범위 또는 경고 | 구체 API 설계 부족 | 범위+경고 채택 |
| 외부 시장 달력 | 제외 | 제외 | 특별 거래시간 때문에 재논의 필요 |
| 환율 변경 | 범위 제외 | 동일성 확인 필요 | 현재 동일 객체 사용, 회귀 테스트만 |
| 복구 UI | CLI dry-run/apply | 동일 | 합의, 채택 |
| 부분 실패 | 종목별 성공 후 commit | 종목별 격리 | fetch 결과 분리 + bulk upsert |
| 다중 프로세스 | 명시 부족 | 명시 부족 | DB 원자 upsert 필수, 현 단일 worker 문서화 |

## 잠정 통합 방향

1. 시장별 quote 수집·검증과 스냅샷 저장을 분리한다.
2. 제공자 거래일만 저장하고 장중 당일 바는 확정하지 않는다.
3. KRX와 US를 별도 job으로 실행한다.
4. 스케줄 누락은 grace와 시작 catch-up 양쪽으로 복구한다.
5. 성공 quote를 PostgreSQL에 원자적 bulk upsert한 뒤 Redis에 반영한다.
6. 전체 기간 일회성 복구 CLI와 짧은 최근 구간 자동 보정을 분리한다.
7. 대시보드 비교일은 종목별 계산하고 시장 내 날짜 범위를 정확히 표시한다.
8. `updated_at`은 관측 용도이며 데이터 진실 판정은 제공자 OHLC 비교로 한다.

## Claude 교차검토에서 답해야 할 쟁점

1. 미국 전용 화~토 06:30 job이 필요한가?
2. 최초 전체 기간 복구가 필요한가, 안전한 축소 범위가 있는가?
3. KRX 특별 거래시간을 달력 의존성 없이 안전하게 처리할 수 있는가?
4. PostgreSQL bulk upsert 후 Redis 갱신 정책에 반대 근거가 있는가?
5. 시장 내 기준일 범위를 API에 노출하는 것이 과설계인가?
