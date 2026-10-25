import { act, renderHook } from '@testing-library/react'
import { expect, it } from 'vitest'
import { todoFixture } from '../../../test/todoFixture'
import type { Todo } from '../types'
import { useTodoFilters } from './useTodoFilters'

const todos: Todo[] = [
  { ...todoFixture, id: 1, title: 'Write report', completed: true },
  { ...todoFixture, id: 2, title: 'Buy milk', priority: 'high' },
]

it('starts with all tasks visible, newest first', () => {
  const { result } = renderHook(() => useTodoFilters(todos))
  expect(result.current.filter).toBe('all')
  expect(result.current.search).toBe('')
  expect(result.current.sort).toBe('newest')
  expect(result.current.visible.map((todo) => todo.id)).toEqual([2, 1])
})

it('updates visible tasks when filter and search change', () => {
  const { result } = renderHook(() => useTodoFilters(todos))
  act(() => result.current.setFilter('completed'))
  expect(result.current.visible.map((todo) => todo.id)).toEqual([1])
  act(() => {
    result.current.setFilter('all')
    result.current.setSearch('milk')
  })
  expect(result.current.visible.map((todo) => todo.id)).toEqual([2])
})

it('applies the selected sort order', () => {
  const { result } = renderHook(() => useTodoFilters(todos))
  act(() => result.current.setSort('priority'))
  expect(result.current.visible.map((todo) => todo.id)).toEqual([2, 1])
})
