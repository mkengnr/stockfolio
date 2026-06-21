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
