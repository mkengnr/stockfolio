import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'
import useSWR from 'swr'
import { GroupManager } from '@/components/groups/GroupManager'
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
  share_token: null,
  share_requires_auth: true,
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
    fireEvent.click(screen.getByLabelText('월급 포함'))
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '그룹 생성' }))
    })

    expect(mockedGroupsApi.create).toHaveBeenCalledWith('rollups', {
      name: '가족 자산',
      color: '#6366f1',
      source_group_ids: ['source-1'],
    })
    expect(mutateRollups).toHaveBeenCalled()
  })

  it('updates label metadata and deletes a rollup', async () => {
    mockedGroupsApi.update.mockResolvedValue({ ...label, name: '핵심 배당' })
    mockedGroupsApi.delete.mockResolvedValue(undefined)
    jest.spyOn(window, 'confirm').mockReturnValue(true)
    render(<GroupManager />)

    fireEvent.click(screen.getByRole('button', { name: '배당 수정' }))
    fireEvent.change(screen.getByLabelText('그룹 이름 수정'), { target: { value: '핵심 배당' } })
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '수정 저장' }))
    })
    expect(mockedGroupsApi.update).toHaveBeenCalledWith('labels', 'label-1', {
      name: '핵심 배당',
      color: '#6366f1',
      description: '',
    })

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '가족 삭제' }))
    })
    expect(mockedGroupsApi.delete).toHaveBeenCalledWith('rollups', 'rollup-1')
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
})
