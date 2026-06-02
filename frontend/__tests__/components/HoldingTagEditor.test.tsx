import '@testing-library/jest-dom'
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import useSWR from 'swr'
import { HoldingTagEditor } from '@/components/holdings/HoldingTagEditor'
import { tagsApi } from '@/lib/api'
import type { Tag } from '@/lib/types'

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  tagsApi: {
    addHolding: jest.fn(),
    removeHolding: jest.fn(),
  },
  fetcher: jest.fn(),
}))

const mockedUseSWR = useSWR as jest.Mock
const mockedTagsApi = tagsApi as jest.Mocked<typeof tagsApi>
const mutate = jest.fn()
const onRefresh = jest.fn()

const tags: Tag[] = [
  {
    id: 'group-1',
    name: '장기 투자',
    color: '#2563eb',
    description: null,
    share_token: null,
    share_requires_auth: false,
    holding_ids: ['holding-1'],
    created_at: '2024-01-01T00:00:00Z',
  },
  {
    id: 'group-2',
    name: '배당주',
    color: '#16a34a',
    description: null,
    share_token: null,
    share_requires_auth: false,
    holding_ids: [],
    created_at: '2024-01-01T00:00:00Z',
  },
]

describe('HoldingTagEditor', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedUseSWR.mockReturnValue({ data: tags, isLoading: false, mutate })
  })

  it('shows the existing group selection state', () => {
    render(<HoldingTagEditor holdingId="holding-1" selectedTagIds={['group-1']} onRefresh={onRefresh} />)

    expect(screen.getByRole('button', { name: /장기 투자/ })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: /배당주/ })).toHaveAttribute('aria-pressed', 'false')
    expect(screen.getByText('제거')).toBeInTheDocument()
  })

  it('adds the holding to an unselected group', async () => {
    mockedTagsApi.addHolding.mockResolvedValue(undefined)
    render(<HoldingTagEditor holdingId="holding-1" selectedTagIds={['group-1']} onRefresh={onRefresh} />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /배당주/ }))
    })

    expect(mockedTagsApi.addHolding).toHaveBeenCalledWith('group-2', 'holding-1')
    await waitFor(() => expect(screen.getByRole('button', { name: /배당주/ })).toHaveAttribute('aria-pressed', 'true'))
    expect(mutate).toHaveBeenCalled()
    expect(onRefresh).toHaveBeenCalled()
  })

  it('removes the holding from a selected group', async () => {
    mockedTagsApi.removeHolding.mockResolvedValue(undefined)
    render(<HoldingTagEditor holdingId="holding-1" selectedTagIds={['group-1']} onRefresh={onRefresh} />)

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /장기 투자/ }))
    })

    expect(mockedTagsApi.removeHolding).toHaveBeenCalledWith('group-1', 'holding-1')
    await waitFor(() => expect(screen.getByRole('button', { name: /장기 투자/ })).toHaveAttribute('aria-pressed', 'false'))
  })

  it('links to group management when no groups exist', () => {
    mockedUseSWR.mockReturnValue({ data: [], isLoading: false, mutate })
    render(<HoldingTagEditor holdingId="holding-1" selectedTagIds={[]} onRefresh={onRefresh} />)

    expect(screen.getByRole('link', { name: '그룹을 먼저 만들어 보세요.' })).toHaveAttribute('href', '/tags')
  })
})
