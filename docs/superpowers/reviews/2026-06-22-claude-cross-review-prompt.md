# Claude 역교차검토 요청

Stockfolio 시장별 종가·스냅샷 개선안의 2차 교차검토를 수행해줘.

이번에는 독립안 단계가 끝났으므로 Codex 문서를 읽어도 된다.

## 읽을 문서

1. `docs/superpowers/reviews/2026-06-22-market-snapshot-evidence.md`
2. `docs/superpowers/reviews/2026-06-22-market-snapshot-codex-proposal.md`
3. `docs/superpowers/reviews/2026-06-22-market-snapshot-claude-proposal.md`
4. `docs/superpowers/reviews/2026-06-22-codex-review-of-claude.md`
5. `docs/superpowers/reviews/2026-06-22-market-snapshot-comparison-draft.md`

필요하면 관련 애플리케이션 코드와 테스트를 다시 읽어 근거를 확인해라. `.env`, 비밀값, 운영 데이터는 읽지 마라.

## 수행할 작업

1. Codex 독립안의 오류, 누락, 과설계를 심각도와 코드 근거를 붙여 지적해라.
2. `2026-06-22-codex-review-of-claude.md`의 C1~C10 각각에 대해 다음 중 하나로 판정해라.
   - 동의
   - 일부 동의
   - 반대
3. 각 판정에는 기술적 근거와 더 나은 대안을 적어라.
4. 비교 초안의 잠정 통합 방향 1~8을 검증해라.
5. 다음 쟁점에 명시적으로 답해라.
   - 미국 전용 화~토 06:30 KST job이 필요한가?
   - 최초 전체 보유 기간 복구가 필요한가?
   - KRX 특별 거래시간을 외부 거래소 달력 없이 안전하게 처리할 수 있는가?
   - PostgreSQL bulk `ON CONFLICT DO UPDATE` 후 Redis 갱신 순서가 타당한가?
   - 시장 내 현재가·비교일 범위를 API에 노출하는 것이 필요한가, 과설계인가?
6. 두 안에서 채택할 항목과 제외할 항목을 표로 정리해라.
7. 최종 통합 설계에 반드시 들어갈 요구사항을 우선순위 순으로 작성해라.
8. 구현은 시작하지 마라.

## 특별 검증 항목

- APScheduler `max_instances=1`은 프로세스 내부에서만 유효하다는 지적이 맞는지 확인해라.
- 현재 운영은 uvicorn 단일 worker지만 DB 쓰기는 다중 실행에도 안전해야 하는지 판단해라.
- 미국 금요일 종가를 기존 월~금 15:35 KST job만으로 적시에 기록할 수 있는지 확인해라.
- 최근 30일 복구가 과거 전체의 잘못된 KST 날짜 스냅샷을 남길 가능성을 확인해라.
- 현재 `build_dashboard_response`에서 summary와 history가 같은 `exchange_rate` 객체를 받는지 확인해라.
- `updated_at`이 과거 오염 데이터의 진실 판정 기준이 될 수 있는지 확인해라.
- KRX 특별 지연 폐장일에 고정 15:30 게이트가 안전한지 확인해라.

## 결과 형식

한국어로 다음 순서를 사용해라.

1. 전체 판정
2. Codex 안의 문제점
3. C1~C10 판정표
4. 잠정 통합 방향 1~8 검증
5. 핵심 쟁점 5개 답변
6. 채택·수정·제외 표
7. 최종 통합안에 필요한 요구사항
8. 남은 불확실성

결과는 다음 파일에만 작성해라.

`docs/superpowers/reviews/2026-06-22-claude-review-of-codex.md`

코드·DB·Redis·서비스를 수정하거나 커밋하지 마라. 문서 작성 후 모순, placeholder, 근거 없는 주장을 자체검토해 바로 수정해라.
