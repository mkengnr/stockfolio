import '@testing-library/jest-dom'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { TransactionClassificationEditor } from '@/components/groups/TransactionClassificationEditor'
import { holdingsApi } from '@/lib/api'
import type { Label, SourceGroup } from '@/lib/types'

jest.mock('@/lib/api', () => ({
  holdingsApi: {
    updateTransactionClassification: jest.fn(),
  },
}))

const mockedHoldingsApi = holdingsApi as jest.Mocked<typeof holdingsApi>

const sourceGroups: SourceGroup[] = [
  {
    id: 'source-1',
    name: '모음통장',
    color: '#2563eb',
    description: null,
    share_token: null,
    share_requires_auth: true,
    created_at: '2026-06-01T00:00:00Z',
  },
]

const labels: Label[] = [
  {
    id: 'label-1',
    name: '장기투자',
    color: '#16a34a',
    description: null,
    share_token: null,
    share_requires_auth: true,
    created_at: '2026-06-01T00:00:00Z',
  },
]

function renderEditor(overrides: Partial<React.ComponentProps<typeof TransactionClassificationEditor>> = {}) {
  const props = {
    holdingId: 'holding-1',
    transactionId: 'tx-1',
    sourceGroups,
    labels,
    sourceGroupId: null,
    labelIds: [] as string[],
    onRefresh: jest.fn(),
    onCancel: jest.fn(),
    ...overrides,
  }
  render(<TransactionClassificationEditor {...props} />)
  return props
}

describe('TransactionClassificationEditor', () => {
  beforeEach(() => {
    jest.clearAllMocks()
  })

  it('submits the edited classification then refreshes and closes', async () => {
    mockedHoldingsApi.updateTransactionClassification.mockResolvedValue(undefined as never)
    const props = renderEditor()

    fireEvent.change(screen.getByLabelText('출처 그룹'), { target: { value: 'source-1' } })
    fireEvent.click(screen.getByRole('button', { name: '분류 저장' }))

    await waitFor(() => {
      expect(mockedHoldingsApi.updateTransactionClassification).toHaveBeenCalledWith(
        'holding-1',
        'tx-1',
        { source_group_id: 'source-1', label_ids: [] },
      )
    })
    expect(props.onRefresh).toHaveBeenCalled()
    expect(props.onCancel).toHaveBeenCalled()
  })

  it('shows the error and stays open when the update fails', async () => {
    mockedHoldingsApi.updateTransactionClassification.mockRejectedValue(new Error('분류 변경 실패'))
    const props = renderEditor()

    fireEvent.click(screen.getByRole('button', { name: '분류 저장' }))

    expect(await screen.findByText('분류 변경 실패')).toBeInTheDocument()
    expect(props.onCancel).not.toHaveBeenCalled()
  })

  it('cancels without calling the api', () => {
    const props = renderEditor()

    fireEvent.click(screen.getByRole('button', { name: '취소' }))

    expect(props.onCancel).toHaveBeenCalled()
    expect(mockedHoldingsApi.updateTransactionClassification).not.toHaveBeenCalled()
  })
})
