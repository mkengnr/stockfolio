# Stockfolio V2 Redesign

## Goal

Stockfolio should answer two questions without forcing the user to reshape their
brokerage account:

1. How is my full portfolio performing?
2. How is a purpose-specific subset performing and how can I share it?

The current implementation already has useful foundations: holdings,
transactions, tags, daily snapshots, OTP sessions, admin-managed users, and
share tokens. V2 keeps these foundations and connects the missing product
flows before introducing larger schema changes.

## Current State Audit

| Requirement | Current state | V2 action |
| --- | --- | --- |
| Register a holding and transactions | Implemented | Add stock search and historical backfill |
| Dashboard summary | Implemented with a data-integrity issue | Split KRW and USD until FX conversion exists |
| Dashboard performance chart | Component exists but is not rendered | Add a portfolio history API and render currency-specific series |
| Per-stock price chart | Component exists | Backfill prices from the first buy date |
| Purpose-specific grouping | Physical `Tag` schema and API exist | Expose group management and holding group editing in the UI |
| Combine multiple groups | Missing | Add saved views after the single-group UX is complete |
| Public or authenticated share | Backend and partial UI exist | Make group management discoverable and clarify shared payload scope |
| Admin allowlisted email users | Implemented | Add operational bootstrap guidance |
| OTP email delivery | Console-only | Add SMTP delivery through environment variables |
| Current intraday quote | Not implemented | Mark delayed quotes clearly; replace the provider when real-time quotes are required |

## Domain Decision

Treat the current `Tag` model as the MVP `Group` primitive.

- A holding may belong to multiple groups, so the same brokerage position can appear
  in multiple purpose-specific views.
- A group remains shareable because it represents a stable named view.
- Do not duplicate holdings when grouping them.

The physical `tags` and `holding_tags` tables can remain during the MVP to avoid
an unnecessary migration while the UX is completed. Rename them to `groups` and
`holding_groups` before introducing real lightweight tags such as `dividend`,
`semiconductor`, or `US`.

Add a `SavedView` concept in a later migration for combinations such as
`club-fund + long-term`. A saved view should reference groups and use an
explicit operator (`ANY` or `ALL`). It should not copy group membership. This
preserves a simple editing model and keeps combinations up to date.

## Data Integrity Rules

1. Never add KRW and USD values directly. Until exchange-rate snapshots exist,
   show separate summaries and chart series per currency.
2. Use the moving-average method consistently and derive historical quantity
   and cost basis from transactions for each day.
   A snapshot stores a close price, not the authoritative historical quantity.
3. Reject sells that exceed the available quantity as of the transaction date.
4. Treat the current providers as delayed-price providers. `pykrx` does not
   satisfy a real-time KRX quote requirement.
5. Backfill daily close prices from `first_buy_date` when a holding is created.

## Delivery Plan

### MVP: Complete The Existing Product

- Send OTP email through SMTP using environment variables only.
- Add stock code/name search and registration autocomplete.
- Expose `/tags`, group creation/deletion, holding group editing, and share entry.
- Add `/api/portfolio/history` and render dashboard chart series by currency.
- Fix the inverted group attachment arguments in the holding registration flow.
- Add rate limiting for OTP request and verification.

### P1: Correct Historical Performance

- Backfill close-price snapshots when registering a holding.
- Rebuild affected history after backdated transactions.
- Validate transaction chronology and overselling.
- Return currency-specific group summaries and shared summaries.
- Add integration tests for ownership, share authentication, and scheduler jobs.

### P2: Composite Views And Production Quotes

- Add saved views combining groups with `ANY` and `ALL`.
- Decide whether saved views can be shared independently.
- Add FX-rate snapshots if a converted total is required.
- Replace delayed quote providers with a provider that meets the real-time SLA.
- Add operational monitoring for mail, quote, scheduler, and cache failures.

## Security And Operations

- The mail app password exposed during planning must be revoked and regenerated.
  Store the replacement only as `SMTP_PASSWORD` in `backend/.env` or the
  deployment secret store. Never commit it.
- Use a production `SECRET_KEY`; the development default must not be deployed.
- Keep cookies `Secure`, `HttpOnly`, and `SameSite=Lax` in production.
- Add request throttling before exposing OTP endpoints outside the local network.
- Review CSRF protection before accepting state-changing cross-origin requests.

## Claude Code Collaboration

This repository already supports Claude Code to Codex review through
`scripts/codex_review.sh`. The reciprocal `scripts/claude_review.sh` command
asks Claude Code for a read-only audit:

```bash
claude auth
./scripts/claude_review.sh "Review the V2 implementation against docs/v2-redesign.md"
```

Claude Code must be authenticated locally before it can participate. Do not
place credentials in prompts, scripts, or committed files.
