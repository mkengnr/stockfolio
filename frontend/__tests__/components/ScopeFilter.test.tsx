import '@testing-library/jest-dom'
import { fireEvent, render, screen } from '@testing-library/react'
import { ScopeFilter, portfolioScopeQuery } from '@/components/dashboard/ScopeFilter'
import { portfolioApi } from '@/lib/api'
import type { Label, RollupGroup, SourceGroup } from '@/lib/types'

const metadata = {
  color: '#6366f1',
  description: null,
  share_token: null,
  share_requires_auth: true,
  share_show_transactions: false,
  created_at: '2026-06-02T00:00:00Z',
}

const sources: SourceGroup[] = [{ id: 'source-1', name: '월급', ...metadata }]
const rollups: RollupGroup[] = [{
  id: 'rollup-1',
  name: '가족',
  source_group_ids: ['source-1'],
  ...metadata,
}]
const labels: Label[] = [{ id: 'label-1', name: '배당', ...metadata }]

describe('ScopeFilter', () => {
  it('offers all, unclassified, source, rollup, and label scopes', () => {
    render(
      <ScopeFilter
        value={{ kind: 'all' }}
        sources={sources}
        rollups={rollups}
        labels={labels}
        onChange={jest.fn()}
      />,
    )

    expect(screen.getByRole('option', { name: '전체 포트폴리오' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '미분류' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '출처: 월급' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '통합: 가족' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: '라벨: 배당' })).toBeInTheDocument()
  })

  it('returns the selected entity scope', () => {
    const onChange = jest.fn()
    render(
      <ScopeFilter
        value={{ kind: 'all' }}
        sources={sources}
        rollups={rollups}
        labels={labels}
        onChange={onChange}
      />,
    )

    fireEvent.change(screen.getByLabelText('대시보드 범위'), {
      target: { value: 'rollup:rollup-1' },
    })

    expect(onChange).toHaveBeenCalledWith({ kind: 'rollup', id: 'rollup-1' })
  })
})

describe('portfolioScopeQuery', () => {
  it('serializes the same selected scope for every dashboard endpoint', () => {
    expect(portfolioScopeQuery({ kind: 'label', id: 'label-1' })).toBe(
      'scope_kind=label&scope_id=label-1',
    )
    expect(portfolioScopeQuery({ kind: 'unclassified' })).toBe('scope_kind=unclassified')
    expect(portfolioApi.summaryPath({ kind: 'label', id: 'label-1' })).toBe(
      '/api/portfolio/summary?scope_kind=label&scope_id=label-1',
    )
    expect(portfolioApi.holdingsPath({ kind: 'label', id: 'label-1' })).toBe(
      '/api/portfolio/holdings?scope_kind=label&scope_id=label-1',
    )
    expect(portfolioApi.historyPath({ kind: 'label', id: 'label-1' })).toBe(
      '/api/portfolio/history?scope_kind=label&scope_id=label-1',
    )
  })
})
