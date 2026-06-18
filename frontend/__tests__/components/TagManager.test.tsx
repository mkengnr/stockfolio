import '@testing-library/jest-dom'
import { act, fireEvent, render, screen } from '@testing-library/react'
import useSWR from 'swr'
import { TagManager } from '@/components/tags/TagManager'
import { tagsApi } from '@/lib/api'
import type { Tag } from '@/lib/types'

jest.mock('swr', () => ({
  __esModule: true,
  default: jest.fn(),
}))

jest.mock('@/lib/api', () => ({
  tagsApi: {
    create: jest.fn(),
    update: jest.fn(),
    delete: jest.fn(),
  },
  fetcher: jest.fn(),
}))

const mockedUseSWR = useSWR as jest.Mock
const mockedTagsApi = tagsApi as jest.Mocked<typeof tagsApi>
const mutate = jest.fn()

const tag: Tag = {
  id: 'group-1',
  name: '장기 투자',
  color: '#2563eb',
  description: '10년 보유',
  share_description: null,
  share_token: null,
  share_requires_auth: false,
  holding_ids: [],
  created_at: '2024-01-01T00:00:00Z',
}

describe('TagManager', () => {
  beforeEach(() => {
    jest.clearAllMocks()
    mockedUseSWR.mockReturnValue({ data: [tag], isLoading: false, mutate })
  })

  it('updates a group from the management page', async () => {
    mockedTagsApi.update.mockResolvedValue(tag)
    render(<TagManager />)

    fireEvent.click(screen.getByRole('button', { name: '수정' }))
    fireEvent.change(screen.getByLabelText('그룹 이름 수정'), { target: { value: '장기 핵심' } })
    fireEvent.change(screen.getByLabelText('설명 수정'), { target: { value: '은퇴 자금' } })
    fireEvent.change(screen.getByLabelText('공유 페이지 문구 수정'), { target: { value: '장기 투자 공유 화면' } })

    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: '수정 저장' }))
    })

    expect(mockedTagsApi.update).toHaveBeenCalledWith('group-1', {
      name: '장기 핵심',
      color: '#2563eb',
      description: '은퇴 자금',
      share_description: '장기 투자 공유 화면',
    })
    expect(mutate).toHaveBeenCalled()
  })
})
