import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import useSWR from 'swr'
import { ColorInput, GroupManager } from '@/components/groups/GroupManager'
import { GROUP_COLOR_PRESETS } from '@/lib/groupColors'
import { groupsApi } from '@/lib/api'
import type { Label, RollupGroup, SourceGroup } from '@/lib/types'

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  fetcher: jest.fn(),
  groupsApi: {
    create: jest.fn(),
    update: jest.fn(),
    delete: jest.fn(),
    enableShare: jest.fn(),
    disableShare: jest.fn(),
  },
}))

const metadata = {
  color: '#6366f1',
  description: null,
  share_description: null,
  share_token: null,
  share_requires_auth: true,
  share_show_transactions: false,
  created_at: '2026-06-02T00:00:00Z',
}

const source: SourceGroup = { id: 'source-1', name: '월급', ...metadata }
const rollup: RollupGroup = {
  id: 'rollup-1',
  name: '가족',
  source_group_ids: ['source-1'],
  ...metadata,
}
const label: Label = { id: 'label-1', name: '배당', ...metadata }
const mockedUseSWR = useSWR as jest.Mock
const mockedGroupsApi = groupsApi as jest.Mocked<typeof groupsApi>
const mutateSources = jest.fn()
const mutateRollups = jest.fn()
const mutateLabels = jest.fn()

describe('GroupManager', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedUseSWR.mockImplementation((key: string) => ({
      '/api/groups/sources': { data: [source], isLoading: false, mutate: mutateSources },
      '/api/groups/rollups': { data: [rollup], isLoading: false, mutate: mutateRollups },
      '/api/groups/labels': { data: [label], isLoading: false, mutate: mutateLabels },
    })[key])
  })

  it('renders source groups, rollup groups, and labels as separate sections', () => {
    render(<GroupManager />)

    expect(screen.getByRole('heading', { name: '출처 그룹' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '통합 그룹' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: '라벨' })).toBeInTheDocument()
  })

  it('creates a rollup with selected source members', async () => {
    mockedGroupsApi.create.mockResolvedValue(rollup)
    render(<GroupManager />)

    fireEvent.change(screen.getByLabelText('그룹 종류'), { target: { value: 'rollups' } })
    fireEvent.change(screen.getByLabelText('그룹 이름'), { target: { value: '가족 자산' } })
    fireEvent.change(screen.getByLabelText('공유 페이지 문구'), { target: { value: '가족용 공유 화면' } })
    fireEvent.click(screen.getByLabelText('월급 포함'))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '그룹 생성' }))
    })

    expect(mockedGroupsApi.create).toHaveBeenCalledWith('rollups', {
      name: '가족 자산',
      // beforeEach has all groups using '#6366f1', so recommendedColor → '#3b82f6' (second preset)
      color: '#3b82f6',
      share_description: '가족용 공유 화면',
      source_group_ids: ['source-1'],
    })
    expect(mutateRollups).toHaveBeenCalled()
  })

  it('updates label metadata and deletes a rollup', async () => {
    mockedGroupsApi.update.mockResolvedValue({ ...label, name: '핵심 배당' })
    mockedGroupsApi.delete.mockResolvedValue(undefined)
    jest.spyOn(window, 'confirm').mockReturnValue(true)
    render(<GroupManager />)

    // Inline edit: find the label card and click 수정 inside it
    const labelCard = screen.getByText('배당').closest('[data-testid="group-card"]') as HTMLElement
    fireEvent.click(within(labelCard).getByRole('button', { name: '배당 수정' }))
    fireEvent.change(within(labelCard).getByLabelText('그룹 이름 수정'), { target: { value: '핵심 배당' } })
    fireEvent.change(within(labelCard).getByLabelText('공유 페이지 문구 수정'), { target: { value: '배당 공유 안내' } })
    await act(async () => {
      fireEvent.click(within(labelCard).getByRole('button', { name: '수정 저장' }))
    })
    expect(mockedGroupsApi.update).toHaveBeenCalledWith('labels', 'label-1', {
      name: '핵심 배당',
      color: '#6366f1',
      description: '',
      share_description: '배당 공유 안내',
    })

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '가족 삭제' }))
    })
    expect(mockedGroupsApi.delete).toHaveBeenCalledWith('rollups', 'rollup-1')
  })

  it('edits a group inline in its own card without a top edit panel', async () => {
    ;(groupsApi.update as jest.Mock).mockResolvedValue({})
    render(<GroupManager />)

    // Find the source group card by its badge text
    const card = screen.getByText('월급').closest('[data-testid="group-card"]') as HTMLElement
    fireEvent.click(within(card).getByRole('button', { name: '월급 수정' }))

    // The inline form should appear inside that card
    const nameInput = within(card).getByLabelText('그룹 이름 수정') as HTMLInputElement
    expect(nameInput).toBeInTheDocument()
    fireEvent.change(nameInput, { target: { value: '새이름' } })
    fireEvent.click(within(card).getByRole('button', { name: '수정 저장' }))

    await waitFor(() =>
      expect(groupsApi.update).toHaveBeenCalledWith(
        'sources',
        'source-1',
        expect.objectContaining({ name: '새이름' }),
      ),
    )

    // No separate top edit panel heading should exist for the inline case
    expect(screen.queryByRole('heading', { name: '출처 그룹 수정' })).not.toBeInTheDocument()
  })

  it('stacks inline edit fields so the color presets stay inside a desktop card', () => {
    render(<GroupManager />)

    const card = screen.getByText('월급').closest('[data-testid="group-card"]') as HTMLElement
    fireEvent.click(within(card).getByRole('button', { name: '월급 수정' }))

    const nameField = within(card).getByLabelText('그룹 이름 수정').parentElement
    const fieldLayout = nameField?.parentElement

    expect(fieldLayout).toHaveClass('flex', 'flex-col', 'gap-4')
    expect(fieldLayout).not.toHaveClass('sm:grid-cols-[1fr_1fr_auto]')
  })

  it('enables and disables sharing for a source group', async () => {
    mockedGroupsApi.enableShare.mockResolvedValue({
      ...source,
      share_token: 'share-token',
      share_requires_auth: false,
    })
    mockedGroupsApi.disableShare.mockResolvedValue(undefined)
    mockedUseSWR.mockImplementation((key: string) => ({
      '/api/groups/sources': { data: [{ ...source, share_token: 'share-token' }], isLoading: false, mutate: mutateSources },
      '/api/groups/rollups': { data: [rollup], isLoading: false, mutate: mutateRollups },
      '/api/groups/labels': { data: [label], isLoading: false, mutate: mutateLabels },
    })[key])
    render(<GroupManager />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '월급 공유 중지' }))
    })
    expect(mockedGroupsApi.disableShare).toHaveBeenCalledWith('sources', 'source-1')
  })

  it('shows a section fetch failure and retries only that section', async () => {
    mockedUseSWR.mockImplementation((key: string) => ({
      '/api/groups/sources': { data: [source], isLoading: false, mutate: mutateSources },
      '/api/groups/rollups': { error: new Error('network failure'), isLoading: false, mutate: mutateRollups },
      '/api/groups/labels': { data: [label], isLoading: false, mutate: mutateLabels },
    })[key])
    render(<GroupManager />)

    expect(screen.getByText('통합 그룹을 불러오지 못했습니다.')).toBeInTheDocument()
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '통합 그룹 다시 시도' }))
    })

    expect(mutateRollups).toHaveBeenCalled()
    expect(mutateSources).not.toHaveBeenCalled()
    expect(mutateLabels).not.toHaveBeenCalled()
  })

  it('defaults a new group color to the first unused preset', () => {
    mockedUseSWR.mockImplementation((key: string) => ({
      '/api/groups/sources': {
        data: [{ ...source, color: '#6366f1' }],
        isLoading: false,
        mutate: mutateSources,
      },
      '/api/groups/rollups': {
        data: [{ ...rollup, color: '#3b82f6' }],
        isLoading: false,
        mutate: mutateRollups,
      },
      '/api/groups/labels': {
        data: [{ ...label, color: '#3b82f6' }],
        isLoading: false,
        mutate: mutateLabels,
      },
    })[key])
    render(<GroupManager />)

    // '#6366f1' and '#3b82f6' are used; first unused preset is '#06b6d4' (시안)
    const colorInput = document.querySelector('input[type="color"][aria-label="그룹 색상"]') as HTMLInputElement
    expect(colorInput).not.toBeNull()
    expect(colorInput.value).toBe('#06b6d4')
  })

  it('shows access indicators and copy and open controls for active share links', () => {
    const writeText = jest.fn()
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText },
    })
    mockedUseSWR.mockImplementation((key: string) => ({
      '/api/groups/sources': {
        data: [{ ...source, share_token: 'public-token', share_requires_auth: false }],
        isLoading: false,
        mutate: mutateSources,
      },
      '/api/groups/rollups': {
        data: [{ ...rollup, share_token: 'login-token', share_requires_auth: true }],
        isLoading: false,
        mutate: mutateRollups,
      },
      '/api/groups/labels': { data: [label], isLoading: false, mutate: mutateLabels },
    })[key])
    render(<GroupManager />)

    expect(screen.getByText('누구나 접근 가능')).toBeInTheDocument()
    expect(screen.getByText('로그인 필요')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '월급 공유 링크 복사' }))
    expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/share/public-token`)
    expect(screen.getByRole('link', { name: '월급 공유 링크 열기' })).toHaveAttribute(
      'href',
      `${window.location.origin}/share/public-token`,
    )
    expect(screen.getByRole('link', { name: '월급 공유 링크 열기' })).toHaveAttribute('target', '_blank')
  })

  it('shows an error inside the card on inline-edit save failure', async () => {
    mockedGroupsApi.update.mockRejectedValue(new Error('저장 실패'))
    render(<GroupManager />)

    // Find the label card and click 수정
    const labelCard = screen.getByText('배당').closest('[data-testid="group-card"]') as HTMLElement
    fireEvent.click(within(labelCard).getByRole('button', { name: '배당 수정' }))

    // Submit the edit form
    await act(async () => {
      fireEvent.click(within(labelCard).getByRole('button', { name: '수정 저장' }))
    })

    // Error message appears INSIDE the card
    expect(within(labelCard).getByText('저장 실패')).toBeInTheDocument()
    // Edit form stays open (name input still present)
    expect(within(labelCard).getByLabelText('그룹 이름 수정')).toBeInTheDocument()
  })
})

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
