# Desktop Group Edit Color Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep the group color picker inside its edited card on desktop while preserving the existing mobile layout and behavior.

**Architecture:** Change only the inline edit form's field wrapper from a breakpoint-driven three-column grid to a vertical flex stack. Add a focused component regression test that checks the edit form's layout contract; leave the create form, card grid, state, and API flows unchanged.

**Tech Stack:** Next.js 14, React 18, TypeScript, Tailwind CSS, Jest, React Testing Library

---

### Task 1: Lock the inline edit layout with a regression test

**Files:**
- Modify: `frontend/__tests__/components/GroupManager.test.tsx`
- Modify: `frontend/components/groups/GroupManager.tsx:426-434`

- [ ] **Step 1: Write the failing test**

Add this test inside `describe('GroupManager', ...)`:

```tsx
it('stacks inline edit fields so the color presets stay inside a desktop card', () => {
  render(<GroupManager />)

  const card = screen.getByText('월급').closest('[data-testid="group-card"]') as HTMLElement
  fireEvent.click(within(card).getByRole('button', { name: '월급 수정' }))

  const nameField = within(card).getByLabelText('그룹 이름 수정').parentElement
  const fieldLayout = nameField?.parentElement

  expect(fieldLayout).toHaveClass('flex', 'flex-col', 'gap-4')
  expect(fieldLayout).not.toHaveClass('sm:grid-cols-[1fr_1fr_auto]')
})
```

- [ ] **Step 2: Run the focused test to verify it fails against the previous desktop grid**

Run:

```bash
cd frontend && npm test -- --runInBand __tests__/components/GroupManager.test.tsx -t "stacks inline edit fields"
```

Expected: FAIL because the wrapper has `grid sm:grid-cols-[1fr_1fr_auto]` instead of `flex flex-col`.

- [ ] **Step 3: Apply the minimal layout fix**

Use this wrapper in the `GroupCard` editing branch:

```tsx
<div className="flex flex-col gap-4">
  <Input label="그룹 이름 수정" value={editName} maxLength={50} onChange={(event) => setEditName(event.target.value)} />
  <Input label="설명 수정" value={editDescription} maxLength={200} onChange={(event) => setEditDescription(event.target.value)} />
  <ColorInput label="그룹 색상 수정" value={editColor} onChange={setEditColor} usedColors={usedColors} />
</div>
```

- [ ] **Step 4: Run the focused test to verify it passes**

Run:

```bash
cd frontend && npm test -- --runInBand __tests__/components/GroupManager.test.tsx -t "stacks inline edit fields"
```

Expected: PASS.

- [ ] **Step 5: Run the complete component test file**

Run:

```bash
cd frontend && npm test -- --runInBand __tests__/components/GroupManager.test.tsx
```

Expected: all `GroupManager` and `ColorInput` tests pass without warnings or errors.

### Task 2: Verify responsive behavior and repository health

**Files:**
- Verify: `frontend/components/groups/GroupManager.tsx`
- Verify: `frontend/__tests__/components/GroupManager.test.tsx`

- [ ] **Step 1: Run frontend lint**

Run:

```bash
cd frontend && npm run lint
```

Expected: exit code 0 with no new lint errors.

- [ ] **Step 2: Run the full frontend test suite**

Run:

```bash
cd frontend && npm test -- --runInBand
```

Expected: all frontend tests pass.

- [ ] **Step 3: Inspect the desktop edit card**

Open the group management page at a desktop viewport, click a group card's `수정` button, and verify:

- name, description, and color controls appear vertically in the edited card;
- all 12 preset swatches remain inside the card boundary;
- the adjacent group card is not covered;
- save and cancel controls remain usable.

- [ ] **Step 4: Inspect the mobile edit card**

At a mobile viewport, verify the same field order and that no horizontal overflow is introduced.

- [ ] **Step 5: Commit the tested fix**

```bash
git add frontend/components/groups/GroupManager.tsx frontend/__tests__/components/GroupManager.test.tsx docs/superpowers/plans/2026-06-22-desktop-group-edit-color-layout.md
git commit -m "fix: 데스크톱 그룹 수정 색상 배치"
```
