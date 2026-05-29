#!/usr/bin/env bash
# codex_review.sh — hermes를 통해 Codex(gpt-5.5)에게 설계/구현 리뷰를 요청
#
# 사용법:
#   ./scripts/codex_review.sh "리뷰 요청 텍스트"
#   ./scripts/codex_review.sh -f path/to/file.py
#   ./scripts/codex_review.sh -d path/to/dir
#   ./scripts/codex_review.sh --diff           # 현재 변경분 리뷰 (staged + unstaged)
#   ./scripts/codex_review.sh --branch main    # main과의 diff 리뷰
#
# 옵션:
#   -f FILE     단일 파일 리뷰
#   -d DIR      디렉터리 전체 리뷰 (트리 + 주요 파일 내용)
#   --diff      git diff 리뷰
#   --branch B  현재 브랜치와 B의 diff 리뷰
#   -o FILE     결과를 파일로 저장 (기본: stdout)
#   -h          도움말

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
OUTPUT_FILE=""
MODE=""
TARGET=""

usage() {
  sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
}

# 리뷰 요청 프롬프트 베이스
REVIEW_INSTRUCTIONS='당신은 시니어 소프트웨어 엔지니어이자 보안 리뷰어입니다.
아래 코드/설계를 다음 관점에서 비판적으로 리뷰하세요:

1. **아키텍처 적절성** — 책임 분리, 결합도, 확장성, 도메인 모델 정합성
2. **보안 취약점** — OWASP Top 10, 인증/인가, 입력 검증, 비밀 관리, 정보 누설
3. **성능** — 쿼리 최적화, N+1, 캐시 전략, 메모리/네트워크 부담
4. **테스트 커버리지** — 누락된 엣지케이스, 통합 테스트 부재, mock 과다 사용
5. **버그/논리 오류** — 경계 조건, 동시성, 타입 안전성

규칙:
- 발견한 문제마다 **심각도 (Critical / High / Medium / Low)** 와 **구체적 위치**와 **개선안**을 제시
- 좋은 점은 짧게 1~2줄로 요약
- 추측 금지. 코드에 근거해서만 지적
- 한국어로 답변, 마크다운 구조 사용
'

while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help) usage ;;
    -f) MODE="file"; TARGET="$2"; shift 2 ;;
    -d) MODE="dir"; TARGET="$2"; shift 2 ;;
    --diff) MODE="diff"; TARGET=""; shift ;;
    --branch) MODE="branch"; TARGET="$2"; shift 2 ;;
    -o) OUTPUT_FILE="$2"; shift 2 ;;
    *)
      if [[ -z "$MODE" ]]; then MODE="text"; TARGET="$1"; shift
      else echo "unknown arg: $1" >&2; exit 1; fi
      ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "에러: 리뷰 대상이 필요합니다. -h 로 도움말 확인" >&2
  exit 1
fi

build_payload() {
  case "$MODE" in
    text)
      printf '%s\n\n## 리뷰 대상\n\n%s\n' "$REVIEW_INSTRUCTIONS" "$TARGET"
      ;;
    file)
      [[ -f "$TARGET" ]] || { echo "파일 없음: $TARGET" >&2; exit 1; }
      printf '%s\n\n## 파일: %s\n\n```\n%s\n```\n' \
        "$REVIEW_INSTRUCTIONS" "$TARGET" "$(cat "$TARGET")"
      ;;
    dir)
      [[ -d "$TARGET" ]] || { echo "디렉터리 없음: $TARGET" >&2; exit 1; }
      printf '%s\n\n## 디렉터리: %s\n\n### 구조\n```\n' \
        "$REVIEW_INSTRUCTIONS" "$TARGET"
      find "$TARGET" -type f \
        \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' \
        -o -name '*.yml' -o -name '*.yaml' -o -name '*.toml' \) \
        -not -path '*/node_modules/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*' \
        -not -path '*/.next/*' | sort
      printf '```\n\n### 주요 파일 내용\n'
      find "$TARGET" -type f \
        \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' \) \
        -not -path '*/node_modules/*' -not -path '*/.venv/*' -not -path '*/__pycache__/*' \
        -not -path '*/.next/*' -not -path '*/__tests__/*' -not -path '*/tests/*' \
        | sort | while read -r f; do
          printf '\n#### %s\n```\n%s\n```\n' "$f" "$(cat "$f")"
        done
      ;;
    diff)
      printf '%s\n\n## 현재 변경분 (git diff)\n\n```diff\n' "$REVIEW_INSTRUCTIONS"
      ( cd "$REPO_ROOT" && git diff HEAD )
      printf '```\n'
      ;;
    branch)
      printf '%s\n\n## %s 대비 변경분\n\n```diff\n' "$REVIEW_INSTRUCTIONS" "$TARGET"
      ( cd "$REPO_ROOT" && git diff "$TARGET"...HEAD )
      printf '```\n'
      ;;
  esac
}

PAYLOAD="$(build_payload)"
PAYLOAD_SIZE=$(printf '%s' "$PAYLOAD" | wc -c | tr -d ' ')

if [[ "$PAYLOAD_SIZE" -gt 200000 ]]; then
  echo "⚠️  페이로드가 너무 큽니다 (${PAYLOAD_SIZE} bytes). 더 작은 단위로 나눠 리뷰하세요." >&2
  exit 1
fi

echo "📤 Codex(gpt-5.5)에게 리뷰 요청 중... (${PAYLOAD_SIZE} bytes)" >&2

# 페이로드를 임시 파일에 쓰고 -z 인자로 전달 (stdin pipe broken 방지)
TMPFILE="$(mktemp -t codex_review.XXXXXX)"
trap 'rm -f "$TMPFILE"' EXIT
printf '%s' "$PAYLOAD" > "$TMPFILE"

RESULT="$(hermes -z "$(cat "$TMPFILE")" \
  -m gpt-5.5 --provider openai-codex --yolo 2>&1)"

if [[ -n "$OUTPUT_FILE" ]]; then
  printf '%s\n' "$RESULT" > "$OUTPUT_FILE"
  echo "✅ 리뷰 결과 저장: $OUTPUT_FILE" >&2
else
  printf '%s\n' "$RESULT"
fi
