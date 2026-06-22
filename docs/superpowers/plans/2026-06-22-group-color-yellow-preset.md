# Group Color Yellow Preset Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the visually redundant purple group preset with a readable yellow preset while preserving the 12-color palette and recommendation behavior.

**Architecture:** Change the final constant entry in `GROUP_COLOR_PRESETS` from purple `#a855f7` to yellow `#ca8a04`. Keep all consumers unchanged because creation, editing, used-color indicators, and recommendations already read from the shared preset array.

**Tech Stack:** TypeScript, Jest, React, Tailwind-derived color tokens

---

### Task 1: Replace purple with yellow

**Files:**
- Modify: `frontend/lib/groupColors.ts`
- Test: `frontend/__tests__/lib/groupColors.test.ts`

- [ ] **Step 1: Write the failing test**

Add this test inside `describe('recommendGroupColor', ...)`:

```ts
it('includes a readable yellow preset', () => {
  expect(GROUP_COLOR_PRESETS).toContainEqual({ value: '#ca8a04', name: '옐로' })
})
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run:

```bash
cd frontend && npm test -- --runInBand __tests__/lib/groupColors.test.ts -t "includes a readable yellow preset"
```

Expected: FAIL because the preset array does not contain `#ca8a04` named `옐로`.

- [ ] **Step 3: Apply the minimal preset replacement**

Replace the final preset entry with:

```ts
{ value: '#ca8a04', name: '옐로' },
```

- [ ] **Step 4: Run the focused and palette tests**

Run:

```bash
cd frontend && npm test -- --runInBand __tests__/lib/groupColors.test.ts
```

Expected: all six tests pass, including the existing 12-distinct-presets guard.

- [ ] **Step 5: Run the complete frontend suite and build/deploy**

Run:

```bash
cd frontend && npm test -- --runInBand --silent
cd .. && ./svc.sh deploy
```

Expected: all frontend tests pass and all Stockfolio services return healthy status.

- [ ] **Step 6: Verify the shared color picker in Chrome**

Open the logged-in group management page, enter inline edit mode, and confirm the last swatch is named `옐로`, uses `#ca8a04`, and the old `퍼플` swatch is absent.

- [ ] **Step 7: Commit**

```bash
git add frontend/lib/groupColors.ts frontend/__tests__/lib/groupColors.test.ts docs/superpowers/plans/2026-06-22-group-color-yellow-preset.md
git commit -m "feat: 그룹 색상에 옐로 프리셋 추가"
```
