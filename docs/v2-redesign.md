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
| Purpose-specific grouping | Legacy holding-level `Tag` schema and API exist | Replace with transaction-level source groups and descriptive labels |
| Combine multiple groups | Missing | Add rollup groups containing source groups |
| Public or authenticated share | Backend and partial UI exist | Share source, rollup, or label scopes without exposing internal IDs |
| Admin allowlisted email users | Implemented | Add operational bootstrap guidance |
| OTP email delivery | Console-only | Add SMTP delivery through environment variables |
| Current intraday quote | Not implemented | Mark delayed quotes clearly; replace the provider when real-time quotes are required |

## Domain Decision

A brokerage holding remains the complete position for one ticker. Purpose-specific
accounting is recorded at the transaction and buy-lot level:

- A source group identifies the actual source of funds, such as `모음통장`.
  Each buy or sell uses one source group, or remains unclassified.
- A rollup group is a reusable view containing multiple source groups, such as
  `가족`. Rollups do not contain other rollups.
- A label is an overlapping descriptive marker, such as `배당` or `반도체`.
  A transaction may have multiple labels.
- Every buy creates one buy lot with original quantity, remaining quantity, unit
  price, owner, holding, and optional source group.
- Every sell selects one or more buy lots from one source group. Stored sell
  allocations must add up to the sell quantity and cannot exceed lot capacity.

Do not duplicate holdings to represent groups. Scoped summaries and history are
derived from the matching buy lots and stored sell allocations. The full
portfolio remains the sum of every classified and unclassified lot.

The physical `tags` and `holding_tags` tables are legacy expand-migration inputs.
They remain temporarily so rollout can be verified before a later contract
migration removes them.

## Data Integrity Rules

1. Never add KRW and USD values directly. Until exchange-rate snapshots exist,
   show separate summaries and chart series per currency.
2. Use the moving-average method consistently and derive historical quantity
   and cost basis from transactions for each day.
   A snapshot stores a close price, not the authoritative historical quantity.
3. Reject sells unless selected buy-lot allocations equal the sell quantity,
   belong to the selected source group, and remain within lot capacity.
4. Check ownership at every holding, transaction, source group, rollup, label,
   buy-lot, and sell-allocation boundary.
5. Treat the current providers as delayed-price providers. `pykrx` does not
   satisfy a real-time KRX quote requirement.
6. Backfill daily close prices from `first_buy_date` when a holding is created.

## Expand And Contract Migration

The expand migration keeps legacy tables available while introducing source
groups, rollups, labels, buy lots, sell allocations, and transaction-level
classification:

1. Copy each legacy `tags` row to a source group with the same metadata.
2. Convert each existing buy transaction into one buy lot.
3. Assign a legacy holding's buy lots to its source group only when the holding
   has exactly one `holding_tags` row.
4. Leave holdings with zero or multiple legacy tags unclassified for manual
   classification.
5. Mark existing sell transactions `requires_review` because their original lot
   selection cannot be reconstructed safely.

Unclassified lots and `requires_review` transactions are expected operational
queues, not migration failures. Operators should review their reported counts
and resolve them through the application. A later contract migration may remove
`tags` and `holding_tags` only after the queues and integrity checks are accepted.

## Delivery Plan

### MVP: Complete The Existing Product

- Send OTP email through SMTP using environment variables only.
- Add stock code/name search and registration autocomplete.
- Expose source-group, rollup-group, label, lot-selection, and scoped-share flows.
- Add `/api/portfolio/history` and render dashboard chart series by currency.
- Fix the inverted group attachment arguments in the holding registration flow.
- Add rate limiting for OTP request and verification.

### P1: Correct Historical Performance

- Backfill close-price snapshots when registering a holding.
- Rebuild affected history after backdated transactions.
- Validate transaction chronology and overselling.
- Return currency-specific group summaries and shared summaries.
- Add integration tests for ownership, share authentication, and scheduler jobs.

### P2: Contract Migration And Production Quotes

- Remove legacy `tags` and `holding_tags` after expand-migration verification.
- Add FX-rate snapshots if a converted total is required.
- Replace delayed quote providers with a provider that meets the real-time SLA.
- Add operational monitoring for mail, quote, scheduler, and cache failures.

## Deployment Verification

Run the read-only verification script after applying migrations:

```bash
backend/.venv/bin/python scripts/verify_group_lot_migration.py
```

The report includes users, holdings, transactions, legacy `holding_tags`, source
groups, rollups, labels, buy lots, sell allocations, unclassified lots,
`requires_review` transactions, cross-owner relation mismatches, and buy-lot
remaining quantity mismatches. Any integrity mismatch exits nonzero. Pending
classification and review queues are printed with explicit counts but do not
fail the command.

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
