# 라벨 필터 + 그룹 색상 추천 + 그룹관리 인라인 수정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 대시보드 그룹 필터에 라벨(온디맨드)을 추가하고, 그룹 생성 색상을 미사용 색으로 추천+프리셋 제공하며, 그룹관리 수정을 카드 제자리 인라인 편집으로 바꾼다.

**Architecture:** 백엔드는 기존 라벨 스코프 엔진(`build_shared_portfolio_dashboard`)을 재사용한 인증 라벨 대시보드 엔드포인트 1개만 추가. 프론트는 `ColorInput`에 프리셋, `GroupFilterMenu`에 섹션, `DashboardOverview`에 라벨 온디맨드 SWR, `GroupCard`에 인라인 편집을 더한다.

**Tech Stack:** FastAPI + SQLAlchemy(async) / Next.js 14 + TypeScript + SWR + Tailwind. 테스트: backend `pytest`, frontend `jest`.

**스펙:** `docs/superpowers/specs/2026-06-19-label-filter-color-picker-group-edit-design.md`

**구현 순서:** Phase B(색상) → Phase C(인라인 수정) → Phase A(라벨 필터). B는 자기완결적이고 C가 B의 ColorInput을 재사용하므로 먼저 한다.

**공통 명령:**
- frontend 테스트: `cd frontend && npm test -- --runInBand <패턴>`
- frontend 빌드: `cd frontend && npm run build`
- backend 테스트: `cd backend && .venv/bin/python -m pytest tests/<파일> -q`

---

## File Structure

- `frontend/lib/groupColors.ts` — **신규**. 프리셋 팔레트 상수 + `recommendGroupColor` 순수 함수.
- `frontend/components/groups/GroupManager.tsx` — 수정. ColorInput 프리셋, 생성 스마트 기본값, 인라인 편집(GroupCard).
- `frontend/components/dashboard/GroupFilterMenu.tsx` — 수정. 섹션 헤더 옵션 지원.
- `frontend/components/dashboard/DashboardOverview.tsx` — 수정. 라벨 섹션 옵션 + 라벨 온디맨드 SWR 렌더.
- `frontend/lib/api.ts` — 수정. `portfolioApi.labelDashboard` 추가.
- `backend/app/routers/portfolio.py` — 수정. `build_shared_portfolio_dashboard`에 `display_currency` 파라미터 + `GET /labels/{label_id}/dashboard` 엔드포인트.
- 테스트: `frontend/__tests__/lib/groupColors.test.ts`(신규), `frontend/__tests__/components/GroupManager.test.tsx`, `frontend/__tests__/dashboard/GroupFilterMenu.test.tsx`(신규), `frontend/__tests__/dashboard/DashboardOverview.test.tsx`, `backend/tests/test_label_dashboard.py`(신규).

---

## Phase B — 그룹 색상 추천 + 프리셋

### Task B1: 프리셋 팔레트 + 추천 헬퍼

**Files:**
- Create: `frontend/lib/groupColors.ts`
- Test: `frontend/__tests__/lib/groupColors.test.ts`

- [ ] **Step 1: 실패 테스트 작성**

Create `frontend/__tests__/lib/groupColors.test.ts`:
```ts
import { GROUP_COLOR_PRESETS, recommendGroupColor } from '@/lib/groupColors'

describe('recommendGroupColor', () => {
  const first = GROUP_COLOR_PRESETS[0].value

  it('returns the first preset when nothing is used', () => {
    expect(recommendGroupColor([])).toBe(first)
  })

  it('skips used presets and returns the first unused one', () => {
    const used = [GROUP_COLOR_PRESETS[0].value, GROUP_COLOR_PRESETS[1].value]
    expect(recommendGroupColor(used)).toBe(GROUP_COLOR_PRESETS[2].value)
  })

  it('normalizes case when comparing used colors', () => {
    const used = [GROUP_COLOR_PRESETS[0].value.toUpperCase()]
    expect(recommendGroupColor(used)).toBe(GROUP_COLOR_PRESETS[1].value)
  })

  it('falls back to the first preset when every preset is used', () => {
    const used = GROUP_COLOR_PRESETS.map((preset) => preset.value)
    expect(recommendGroupColor(used)).toBe(first)
  })

  it('exposes twelve distinct presets', () => {
    const values = GROUP_COLOR_PRESETS.map((preset) => preset.value.toLowerCase())
    expect(values).toHaveLength(12)
    expect(new Set(values).size).toBe(12)
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm test -- --runInBand groupColors`
Expected: FAIL — `Cannot find module '@/lib/groupColors'`.

- [ ] **Step 3: 구현**

Create `frontend/lib/groupColors.ts`:
```ts
export interface GroupColorPreset {
  value: string
  name: string
}

export const GROUP_COLOR_PRESETS: GroupColorPreset[] = [
  { value: '#6366f1', name: '인디고' },
  { value: '#3b82f6', name: '블루' },
  { value: '#06b6d4', name: '시안' },
  { value: '#14b8a6', name: '틸' },
  { value: '#10b981', name: '에메랄드' },
  { value: '#84cc16', name: '라임' },
  { value: '#f59e0b', name: '앰버' },
  { value: '#f97316', name: '오렌지' },
  { value: '#ef4444', name: '레드' },
  { value: '#ec4899', name: '핑크' },
  { value: '#8b5cf6', name: '바이올렛' },
  { value: '#a855f7', name: '퍼플' },
]

// 전체 그룹에서 아직 안 쓰는 첫 프리셋 색을 추천. 전부 사용 중이면 첫 프리셋.
export function recommendGroupColor(usedColors: string[]): string {
  const used = new Set(usedColors.map((color) => color.trim().toLowerCase()))
  const unused = GROUP_COLOR_PRESETS.find((preset) => !used.has(preset.value.toLowerCase()))
  return (unused ?? GROUP_COLOR_PRESETS[0]).value
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm test -- --runInBand groupColors`
Expected: PASS (5 tests).

- [ ] **Step 5: 커밋**

```bash
git add frontend/lib/groupColors.ts frontend/__tests__/lib/groupColors.test.ts
git commit -m "feat: 그룹 색상 프리셋 팔레트 + 미사용 색 추천 헬퍼"
```

---

### Task B2: ColorInput 프리셋 스와치

**Files:**
- Modify: `frontend/components/groups/GroupManager.tsx` (`ColorInput`, 현재 `:248-261`)
- Test: `frontend/__tests__/components/GroupManager.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`frontend/__tests__/components/GroupManager.test.tsx`에 추가(파일 상단 import에 `import { ColorInput } from '@/components/groups/GroupManager'` 필요 — Step 3에서 `ColorInput`을 `export`로 바꾼다). 새 describe 블록 추가:
```tsx
import { render, screen, fireEvent } from '@testing-library/react'
import { ColorInput } from '@/components/groups/GroupManager'
import { GROUP_COLOR_PRESETS } from '@/lib/groupColors'

describe('ColorInput presets', () => {
  it('renders a swatch button per preset and selects on click', () => {
    const onChange = jest.fn()
    render(<ColorInput label="그룹 색상" value="#6366f1" onChange={onChange} usedColors={[]} />)

    const second = GROUP_COLOR_PRESETS[1]
    const swatch = screen.getByRole('button', { name: new RegExp(second.name) })
    fireEvent.click(swatch)
    expect(onChange).toHaveBeenCalledWith(second.value)
  })

  it('marks used colors as 사용중', () => {
    render(
      <ColorInput
        label="그룹 색상"
        value="#6366f1"
        onChange={() => {}}
        usedColors={[GROUP_COLOR_PRESETS[0].value]}
      />,
    )
    const firstSwatch = screen.getByRole('button', { name: new RegExp(`${GROUP_COLOR_PRESETS[0].name}.*사용중`) })
    expect(firstSwatch).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm test -- --runInBand GroupManager`
Expected: FAIL — `ColorInput` is not exported / no preset buttons.

- [ ] **Step 3: 구현**

`GroupManager.tsx` 상단 import에 추가:
```tsx
import { GROUP_COLOR_PRESETS, recommendGroupColor } from '@/lib/groupColors'
```

`ColorInput`을 export + 프리셋 스와치로 교체 (`:248-261` 전체 대체):
```tsx
export function ColorInput({
  label,
  value,
  onChange,
  usedColors = [],
}: {
  label: string
  value: string
  onChange: (value: string) => void
  usedColors?: string[]
}) {
  const used = new Set(usedColors.map((color) => color.trim().toLowerCase()))
  return (
    <div className="flex flex-col gap-2 text-sm font-medium text-gray-700">
      {label}
      <div className="flex flex-wrap gap-1.5" role="group" aria-label={`${label} 프리셋`}>
        {GROUP_COLOR_PRESETS.map((preset) => {
          const selected = preset.value.toLowerCase() === value.toLowerCase()
          const isUsed = used.has(preset.value.toLowerCase())
          return (
            <button
              key={preset.value}
              type="button"
              aria-label={`${preset.name}${isUsed ? ' (사용중)' : ''}`}
              aria-pressed={selected}
              onClick={() => onChange(preset.value)}
              className={`relative h-7 w-7 rounded-md border transition-transform ${
                selected ? 'ring-2 ring-offset-1 ring-gray-700' : 'border-gray-200'
              } ${isUsed ? 'opacity-40' : ''}`}
              style={{ backgroundColor: preset.value }}
            >
              {isUsed && <span aria-hidden className="absolute inset-0 flex items-center justify-center text-[11px] text-white">✓</span>}
            </button>
          )
        })}
      </div>
      <input
        aria-label={label}
        type="color"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="h-[34px] w-16 cursor-pointer rounded-lg border border-gray-300 bg-white px-1"
      />
    </div>
  )
}
```

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm test -- --runInBand GroupManager`
Expected: PASS (기존 GroupManager 테스트 + 새 ColorInput 2건).

- [ ] **Step 5: 커밋**

```bash
git add frontend/components/groups/GroupManager.tsx frontend/__tests__/components/GroupManager.test.tsx
git commit -m "feat: ColorInput에 그룹 색상 프리셋 스와치 추가"
```

---

### Task B3: 생성 폼 스마트 기본값 + usedColors 주입

**Files:**
- Modify: `frontend/components/groups/GroupManager.tsx` (생성 폼 `:170-204`, 상태 `:30`)
- Test: `frontend/__tests__/components/GroupManager.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`GroupManager.test.tsx`에 추가. 기존 파일에 SWR/`groupsApi` mock 패턴이 있으면 재사용; 없으면 아래처럼 mock:
```tsx
import { render, screen, waitFor } from '@testing-library/react'
import { GroupManager } from '@/components/groups/GroupManager'
import { groupsApi } from '@/lib/api'

jest.mock('@/lib/api', () => ({
  fetcher: (path: string) => (mockData as Record<string, unknown>)[path],
  groupsApi: { create: jest.fn(), update: jest.fn(), delete: jest.fn(), enableShare: jest.fn(), disableShare: jest.fn() },
}))

const mockData: Record<string, unknown> = {
  '/api/groups/sources': [{ id: 's1', name: '카카오', color: '#6366f1', description: null, share_token: null, share_requires_auth: false, share_description: null }],
  '/api/groups/rollups': [],
  '/api/groups/labels': [{ id: 'l1', name: '배당', color: '#3b82f6', description: null, share_token: null, share_requires_auth: false, share_description: null }],
}

it('defaults a new group color to the first unused preset', async () => {
  render(<GroupManager />)
  await waitFor(() => expect(screen.getByText('카카오')).toBeInTheDocument())
  // 사용중: #6366f1(인디고), #3b82f6(블루) → 추천 기본값 = #06b6d4(시안)
  const colorInput = screen.getByLabelText('그룹 색상') as HTMLInputElement
  expect(colorInput.value).toBe('#06b6d4')
})
```
(주의: SWR mock은 프로젝트의 기존 GroupManager 테스트 방식에 맞춰 조정. 기존 테스트가 `useSWR`을 직접 mock하면 그 패턴을 따른다.)

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm test -- --runInBand GroupManager`
Expected: FAIL — 기본값이 `#6366f1`.

- [ ] **Step 3: 구현**

`GroupManager.tsx`에서 사용중 색 집합 계산 + 생성 폼 ColorInput에 주입 + 생성 모드 진입 시 기본값 추천.

`sources`/`rollups`/`labels` 데이터를 모은 뒤(`:43` 근처) 추가:
```tsx
const rollups = rollupsState.data ?? []
const labels = labelsState.data ?? []
const usedColors = [...sources, ...rollups, ...labels].map((group) => group.color)
```

`color` 초기 상태를 추천값으로 동기화. `useEffect`로 데이터 로드 후 생성 폼 색이 기본(DEFAULT_COLOR)이면 추천값으로 1회 세팅:
```tsx
const recommendedColor = recommendGroupColor(usedColors)
useEffect(() => {
  setColor((current) => (current === DEFAULT_COLOR ? recommendedColor : current))
}, [recommendedColor])
```
(파일 상단 `useState` import 옆에 `useEffect` 추가.)

생성 폼 ColorInput(`:187`)에 `usedColors` 전달:
```tsx
<ColorInput label="그룹 색상" value={color} onChange={setColor} usedColors={usedColors} />
```

생성 성공 후 폼 리셋 지점에서 `setColor(recommendedColor)`로 되돌린다(기존 `setColor(DEFAULT_COLOR)` 호출을 `setColor(recommendGroupColor(usedColors))`로 교체 — 다음 생성 때 다음 미사용 색).

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm test -- --runInBand GroupManager`
Expected: PASS.

- [ ] **Step 5: 빌드 + 커밋**

```bash
cd frontend && npm run build
git add frontend/components/groups/GroupManager.tsx frontend/__tests__/components/GroupManager.test.tsx
git commit -m "feat: 새 그룹 색상 기본값을 미사용 프리셋으로 추천"
```

---

## Phase C — 그룹관리 인라인 수정

### Task C1: 카드 제자리 인라인 편집

**Files:**
- Modify: `frontend/components/groups/GroupManager.tsx` (상단 수정카드 `:206-231` 제거, `GroupCard` `:356+`에 인라인 폼, 부모 edit 상태/`handleUpdate` 정리)
- Test: `frontend/__tests__/components/GroupManager.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

```tsx
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

it('edits a group inline in its own card without a top edit panel', async () => {
  ;(groupsApi.update as jest.Mock).mockResolvedValue({})
  render(<GroupManager />)
  await waitFor(() => expect(screen.getByText('카카오')).toBeInTheDocument())

  const card = screen.getByText('카카오').closest('[data-testid="group-card"]') as HTMLElement
  fireEvent.click(within(card).getByRole('button', { name: '수정' }))

  // 편집 폼이 같은 카드 안에 나타난다
  const nameInput = within(card).getByLabelText(/그룹 이름 수정/) as HTMLInputElement
  expect(nameInput).toBeInTheDocument()
  fireEvent.change(nameInput, { target: { value: '카카오페이' } })
  fireEvent.click(within(card).getByRole('button', { name: '수정 저장' }))

  await waitFor(() => expect(groupsApi.update).toHaveBeenCalledWith(
    'sources', 's1', expect.objectContaining({ name: '카카오페이' }),
  ))
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm test -- --runInBand GroupManager`
Expected: FAIL — 카드 안에 수정 폼/`data-testid="group-card"` 없음.

- [ ] **Step 3: 구현**

부모(`GroupManager`)에서 제거: `editing`, `editName`, `editDescription`, `editShareDescription`, `editColor`, `editMemberIds`, `startEdit`, 상단 `{editing && <Card>…수정…</Card>}` 블록(`:206-231`). `handleUpdate` 본문을 콜백으로 재구성:
```tsx
async function handleSave(
  groupKind: GroupKind,
  group: Group,
  payload: { name: string; description: string; share_description: string; color: string; member_ids?: string[] },
) {
  setUpdating(true)
  setError('')
  try {
    await groupsApi.update(groupKind, group.id, {
      name: payload.name.trim(),
      description: payload.description.trim() || null,
      share_description: payload.share_description.trim() || null,
      color: payload.color,
      ...(groupKind === 'rollups' ? { source_group_ids: payload.member_ids ?? [] } : {}),
    })
    await refresh(groupKind)
    return true
  } catch (err) {
    setError(err instanceof Error ? err.message : '그룹을 수정하지 못했습니다.')
    return false
  } finally {
    setUpdating(false)
  }
}
```
(실제 `groupsApi.update` 페이로드 키는 기존 `handleUpdate`가 보내던 키와 동일하게 맞춘다 — 기존 코드 확인 후 정렬.)

`GroupSection`/`GroupCard`에 `sources`, `usedColors`, `onSave`, `updating` prop 전달. `GroupCard`에 로컬 편집 상태 추가:
```tsx
function GroupCard({ kind, group, sources, usedColors, pendingAction, onSave, updating, onDelete, onEnableShare, onDisableShare }: GroupCardProps) {
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState(group.name)
  const [description, setDescription] = useState(group.description ?? '')
  const [shareDescription, setShareDescription] = useState(group.share_description ?? '')
  const [color, setColor] = useState(group.color)
  const [memberIds, setMemberIds] = useState<string[]>(
    kind === 'rollups' ? (group as RollupGroup).source_group_ids : [],
  )

  function startEdit() {
    setName(group.name); setDescription(group.description ?? '')
    setShareDescription(group.share_description ?? ''); setColor(group.color)
    setMemberIds(kind === 'rollups' ? (group as RollupGroup).source_group_ids : [])
    setEditing(true)
  }

  async function save() {
    const ok = await onSave(kind, group, { name, description, share_description: shareDescription, color, member_ids: memberIds })
    if (ok) setEditing(false)
  }

  return (
    <Card data-testid="group-card" className="flex flex-col gap-3">
      {editing ? (
        <form className="flex flex-col gap-3" onSubmit={(e) => { e.preventDefault(); void save() }}>
          <Input label="그룹 이름 수정" value={name} maxLength={50} onChange={(e) => setName(e.target.value)} />
          <Input label="설명 수정" value={description} maxLength={200} onChange={(e) => setDescription(e.target.value)} />
          <ColorInput label="그룹 색상 수정" value={color} onChange={setColor} usedColors={usedColors} />
          <Input label="공유 페이지 문구 수정" value={shareDescription} maxLength={200} onChange={(e) => setShareDescription(e.target.value)} />
          {kind === 'rollups' && <MemberSelector sources={sources} selectedIds={memberIds} onChange={setMemberIds} />}
          <div className="flex gap-2">
            <Button type="submit" loading={updating} disabled={!name.trim()}>수정 저장</Button>
            <Button type="button" variant="secondary" onClick={() => setEditing(false)}>취소</Button>
          </div>
        </form>
      ) : (
        <>
          {/* 기존 카드 본문(Badge/설명/공유블록)을 그대로 유지하고, 기존 onEdit 버튼을 startEdit로 교체 */}
        </>
      )}
    </Card>
  )
}
```
기존 카드 본문의 "수정" 버튼 `onClick`을 `startEdit`로 바꾼다(부모 `onEdit` prop 제거). `Card`가 `data-testid`를 전달하도록 `Card` 컴포넌트가 `...props`를 받는지 확인 — 안 받으면 `Card`를 감싸는 외곽 div에 `data-testid="group-card"`를 둔다.

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm test -- --runInBand GroupManager`
Expected: PASS.

- [ ] **Step 5: 빌드 + 커밋**

```bash
cd frontend && npm run build
git add frontend/components/groups/GroupManager.tsx frontend/__tests__/components/GroupManager.test.tsx
git commit -m "feat: 그룹관리 수정을 카드 제자리 인라인 편집으로 변경"
```

---

## Phase A — 라벨 그룹 필터

### Task A1: 백엔드 라벨 대시보드 엔드포인트

**Files:**
- Modify: `backend/app/routers/portfolio.py` (`build_shared_portfolio_dashboard` `:1364`, 새 엔드포인트 `/dashboard` `:1548` 아래)
- Test: `backend/tests/test_label_dashboard.py` (신규)

- [ ] **Step 1: 실패 테스트 작성**

Create `backend/tests/test_label_dashboard.py`. 기존 `tests/test_groups_api.py`의 client/db 픽스처 + 라벨 생성 패턴을 참고해 작성:
```python
import uuid


def test_label_dashboard_requires_ownership(client, user, db):
    other_label_id = str(uuid.uuid4())
    response = client.get(f"/api/portfolio/labels/{other_label_id}/dashboard")
    assert response.status_code == 404


def test_label_dashboard_returns_scoped_response(client, user, db):
    # 라벨 생성
    created = client.post("/api/groups/labels", json={"name": "배당주", "color": "#f59e0b"})
    assert created.status_code == 201
    label_id = created.json()["id"]

    response = client.get(f"/api/portfolio/labels/{label_id}/dashboard?display_currency=KRW")
    assert response.status_code == 200
    payload = response.json()
    assert "summary" in payload
    assert "history" in payload
    assert "holdings" in payload
    assert payload["groups"] == []
```
(실제 픽스처 이름/인증 헤더는 `test_groups_api.py`와 일치시킨다.)

- [ ] **Step 2: 실패 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_label_dashboard.py -q`
Expected: FAIL — 404 라우트 없음 / 422.

- [ ] **Step 3: 구현**

`build_shared_portfolio_dashboard`(`:1364`)에 `display_currency` 파라미터 추가(기본 "KRW", 기존 호출 호환):
```python
async def build_shared_portfolio_dashboard(
    db: AsyncSession,
    user_id: uuid.UUID,
    scope: PortfolioScope,
    display_currency: DisplayCurrency = "KRW",
) -> DashboardResponse:
```
내부의 USD 환율 분기와 `build_dashboard_response(... display_currency="KRW" ...)`를 `display_currency` 파라미터로 교체:
```python
    if display_currency == "KRW" and any(holding.currency == Currency.USD for holding in holdings):
        try:
            exchange_rate = await asyncio.to_thread(get_usd_krw_rate)
        except Exception as exc:
            logger.warning("scoped USD/KRW exchange rate lookup failed: %r", exc)
            warnings.append("USD/KRW exchange rate lookup failed")
    ...
    return build_dashboard_response(
        ...,
        display_currency=display_currency,
        ...,
    )
```

`/dashboard` 엔드포인트(`:1548`) 아래에 라벨 엔드포인트 추가:
```python
@router.get("/labels/{label_id}/dashboard", response_model=DashboardResponse)
async def get_label_dashboard(
    label_id: uuid.UUID,
    display_currency: DisplayCurrency = "KRW",
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    scope = await resolve_portfolio_scope(db, current_user.id, "label", label_id)
    return await build_shared_portfolio_dashboard(db, current_user.id, scope, display_currency)
```

- [ ] **Step 4: 통과 확인**

Run: `cd backend && .venv/bin/python -m pytest tests/test_label_dashboard.py tests/test_groups_api.py -q`
Expected: PASS (기존 share 테스트 포함 — `build_shared_portfolio_dashboard` 시그니처 호환).

- [ ] **Step 5: 커밋**

```bash
git add backend/app/routers/portfolio.py backend/tests/test_label_dashboard.py
git commit -m "feat: 인증 라벨 스코프 대시보드 엔드포인트 추가"
```

---

### Task A2: 프론트 api + 타입

**Files:**
- Modify: `frontend/lib/api.ts` (`portfolioApi` `:76`)

- [ ] **Step 1: 구현 (단순 추가, 테스트는 A4에서 통합 검증)**

`portfolioApi`에 추가:
```ts
  labelDashboardPath: (labelId: string, displayCurrency: DisplayCurrency = 'KRW') =>
    `/api/portfolio/labels/${labelId}/dashboard?display_currency=${displayCurrency}`,
  labelDashboard: (labelId: string, displayCurrency: DisplayCurrency = 'KRW') =>
    request<DashboardResponse>(portfolioApi.labelDashboardPath(labelId, displayCurrency)),
```

- [ ] **Step 2: 타입체크**

Run: `cd frontend && npm run build`
Expected: ✓ Compiled successfully.

- [ ] **Step 3: 커밋**

```bash
git add frontend/lib/api.ts
git commit -m "feat: portfolioApi.labelDashboard 추가"
```

---

### Task A3: GroupFilterMenu 섹션 지원

**Files:**
- Modify: `frontend/components/dashboard/GroupFilterMenu.tsx`
- Test: `frontend/__tests__/dashboard/GroupFilterMenu.test.tsx` (신규)

- [ ] **Step 1: 실패 테스트 작성**

Create `frontend/__tests__/dashboard/GroupFilterMenu.test.tsx`:
```tsx
import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { GroupFilterMenu } from '@/components/dashboard/GroupFilterMenu'

const options = [
  { value: 'total', label: '전체' },
  { value: 'source:1', label: '카카오', section: '출처 그룹' },
  { value: 'label:9', label: '배당주', section: '라벨' },
]

it('renders section headers and selects an option', () => {
  const onChange = jest.fn()
  render(<GroupFilterMenu value="total" options={options} onChange={onChange} />)
  fireEvent.click(screen.getByRole('button', { name: /그룹 필터/ }))
  expect(screen.getByText('라벨')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('option', { name: /배당주/ }))
  expect(onChange).toHaveBeenCalledWith('label:9')
})
```

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm test -- --runInBand GroupFilterMenu`
Expected: FAIL — section 헤더 미렌더 / 타입.

- [ ] **Step 3: 구현**

`GroupFilterMenu.tsx`의 `GroupFilterOption`에 `section?: string` 추가하고, 옵션 렌더 루프에서 직전 옵션과 `section`이 달라지면 헤더 행을 먼저 렌더:
```tsx
export interface GroupFilterOption {
  value: string
  label: string
  section?: string
}
```
리스트 렌더(`:43-61`)를 교체:
```tsx
{options.map((option, index) => {
  const active = option.value === selected?.value
  const showHeader = option.section && option.section !== options[index - 1]?.section
  return (
    <div key={option.value}>
      {showHeader && (
        <div className="px-3 pb-1 pt-2 text-[11px] font-medium uppercase tracking-wide text-gray-400">
          {option.section}
        </div>
      )}
      <button
        type="button"
        role="option"
        aria-selected={active}
        onClick={() => select(option.value)}
        className={cn(
          'flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm transition-colors',
          active ? 'bg-brand-50 font-medium text-brand-700' : 'text-gray-700 hover:bg-gray-50',
        )}
      >
        <span className="truncate">{option.label}</span>
        {active && <span className="text-xs" aria-hidden>*</span>}
      </button>
    </div>
  )
})}
```

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm test -- --runInBand GroupFilterMenu`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add frontend/components/dashboard/GroupFilterMenu.tsx frontend/__tests__/dashboard/GroupFilterMenu.test.tsx
git commit -m "feat: GroupFilterMenu 섹션 헤더 옵션 지원"
```

---

### Task A4: DashboardOverview 라벨 온디맨드 통합

**Files:**
- Modify: `frontend/components/dashboard/DashboardOverview.tsx`
- Test: `frontend/__tests__/dashboard/DashboardOverview.test.tsx`

- [ ] **Step 1: 실패 테스트 작성**

`DashboardOverview.test.tsx`에 추가. 컴포넌트가 `labels`를 어디서 받는지(prop vs SWR)에 맞춰 mock. 라벨 옵션을 추가하려면 DashboardOverview가 라벨 목록을 알아야 하므로 `labels` prop을 추가한다(아래 구현 참조). 테스트:
```tsx
import { portfolioApi } from '@/lib/api'

jest.mock('@/lib/api', () => ({
  portfolioApi: { labelDashboard: jest.fn() },
}))

it('fetches the label dashboard on demand when a label is selected', async () => {
  ;(portfolioApi.labelDashboard as jest.Mock).mockResolvedValue({
    ...baseDashboard,
    summary: { ...baseDashboard.summary, total_current_value: '999' },
    groups: [],
  })
  render(<DashboardOverview dashboard={baseDashboard} labels={[{ id: '9', name: '배당주', color: '#f59e0b' }]} displayCurrency="KRW" />)

  fireEvent.click(screen.getByRole('button', { name: /그룹 필터/ }))
  fireEvent.click(screen.getByRole('option', { name: /배당주/ }))

  await waitFor(() => expect(portfolioApi.labelDashboard).toHaveBeenCalledWith('9', 'KRW'))
})
```
(`baseDashboard`는 기존 DashboardOverview 테스트 픽스처를 재사용. `labels` prop이 없으면 추가.)

- [ ] **Step 2: 실패 확인**

Run: `cd frontend && npm test -- --runInBand DashboardOverview`
Expected: FAIL — 라벨 옵션 없음 / labelDashboard 미호출.

- [ ] **Step 3: 구현**

`DashboardOverview`에 `labels` prop(`{ id: string; name: string; color: string }[]`, 기본 `[]`) 추가. 라벨 선택 시 SWR로 라벨 대시보드 조회:
```tsx
import useSWR from 'swr'
import { portfolioApi } from '@/lib/api'

const selectedLabelId = selectedGroupKey.startsWith('label:') ? selectedGroupKey.slice('label:'.length) : null
const { data: labelDashboard, isLoading: labelLoading } = useSWR(
  selectedLabelId ? ['label-dashboard', selectedLabelId, displayCurrency] : null,
  () => portfolioApi.labelDashboard(selectedLabelId as string, displayCurrency),
)
const labelMode = selectedLabelId !== null
```

`groupFilterOptions`(`:28-33`)를 섹션 포함으로 확장:
```tsx
const groupFilterOptions = useMemo(() => [
  { value: 'total', label: '전체' },
  ...dashboard.groups
    .filter((g) => g.kind === 'source' || g.kind === 'unclassified')
    .map((g) => ({ value: groupKey(g), label: g.name, section: '출처 그룹' })),
  ...dashboard.groups
    .filter((g) => g.kind === 'combined')
    .map((g) => ({ value: groupKey(g), label: g.name, section: '통합 그룹' })),
  ...labels.map((label) => ({ value: `label:${label.id}`, label: label.name, section: '라벨' })),
], [dashboard.groups, labels])
```
(`groupKey`/`g.kind` 값은 기존 구현과 정확히 일치시킨다.)

`selected*` 파생값을 라벨 모드에서 라벨 응답으로 분기:
```tsx
const activeSummary = labelMode ? (labelDashboard?.summary ?? dashboard.summary) : selectedSummary
const activeHoldings = labelMode ? (labelDashboard?.holdings ?? []) : selectedHoldings
const activeHistoryRows = useMemo(() => {
  if (labelMode) {
    return (labelDashboard?.history.rows ?? []).filter((row) => row.group_kind === 'total')
  }
  return selectedHistoryRows
}, [labelMode, labelDashboard, selectedHistoryRows])
```
렌더에서 `selectedSummary`→`activeSummary`, `selectedHoldings`→`activeHoldings`, `selectedHistoryRows`→`activeHistoryRows`로 교체. 차트:
```tsx
<PortfolioChart
  historyRows={activeHistoryRows}
  compositionRows={dashboard.history.rows}
  includeComposition={!selectedGroup && !labelMode}
  displayCurrency={displayCurrency}
  visibleRange={chartVisibleRange}
  referenceDefault="invested"
/>
```
라벨 로딩 중에는 차트/요약 영역 위에 로딩 표시(예: `{labelLoading && <p className="text-sm text-gray-400">라벨 데이터를 불러오는 중…</p>}`).

비교 테이블(`GroupPerformanceTable`)은 `dashboard.groups`만 사용하므로 라벨은 자동 미포함 — 변경 없음.

`DashboardOverview`를 렌더하는 상위(예: `app/page.tsx` 또는 dashboard 페이지)에서 `labels`를 SWR(`groupsApi.listLabels`)로 받아 prop으로 전달. 해당 페이지 파일을 찾아 `labels={labels ?? []}` 추가.

- [ ] **Step 4: 통과 확인**

Run: `cd frontend && npm test -- --runInBand DashboardOverview`
Expected: PASS.

- [ ] **Step 5: 전체 테스트 + 빌드 + 커밋**

```bash
cd frontend && npm test -- --runInBand && npm run build
git add frontend/components/dashboard/DashboardOverview.tsx frontend/__tests__/dashboard/DashboardOverview.test.tsx frontend/app
git commit -m "feat: 대시보드 그룹 필터에 라벨 온디맨드 추가"
```

---

## 최종 검증

- [ ] backend: `cd backend && .venv/bin/python -m pytest tests/ -q` (기존 339+ 유지 + 신규 통과)
- [ ] frontend: `cd frontend && npm test -- --runInBand` 전체 green
- [ ] frontend: `cd frontend && npm run build` 성공
- [ ] 프리뷰 수동 확인: 새 그룹 색상 추천/프리셋, 그룹관리 인라인 수정(점프 없음), 대시보드 라벨 필터 선택 시 라벨 스코프 표시
- [ ] `git diff --check`

---

## Self-Review 메모

- 스펙 A/B/C 모든 요구사항이 Task로 매핑됨: A→A1~A4, B→B1~B3, C→C1.
- `recommendGroupColor`·`ColorInput(usedColors)`·`GroupFilterMenu(section)`·`labelDashboard`·`get_label_dashboard` 시그니처가 태스크 간 일관됨.
- 비범위(공유 페이지 라벨, 다중 라벨, 색 강제 금지)는 의도적으로 제외.
- 실행 시 주의: 기존 GroupManager/DashboardOverview 테스트의 mock 패턴(useSWR 직접 mock 여부)과 `groupsApi.update` 페이로드 키, `groupKey()`/`group.kind` 실제 값은 구현 직전 현재 코드로 재확인 후 정렬할 것.
