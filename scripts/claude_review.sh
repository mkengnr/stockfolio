#!/usr/bin/env bash
# claude_review.sh - ask Claude Code for a read-only repository audit
#
# Usage:
#   ./scripts/claude_review.sh "Review request"

set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 \"review request\"" >&2
  exit 1
fi

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REQUEST="$*"

cd "$REPO_ROOT"

claude -p \
  --permission-mode dontAsk \
  --tools "Read,Glob,Grep" \
  --max-budget-usd 0.50 \
  "Read CLAUDE.md and docs/v2-redesign.md. Review this trusted repository in read-only mode. ${REQUEST}

Report findings in Korean. Separate Critical, High, Medium, and Low issues.
For every finding, cite concrete file paths and explain a practical fix.
Do not edit files. Do not print secrets."
