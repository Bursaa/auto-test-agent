import { afterEach, expect, it, vi } from 'vitest'
import { request } from './http'

const fetchMock = vi.fn()
vi.stubGlobal('fetch', fetchMock)
afterEach(() => fetchMock.mockReset())

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status })
}

it('prefixes the path, sends JSON headers and parses the response', async () => {
  fetchMock.mockResolvedValue(jsonResponse({ ok: true }))
  await expect(
    request('/todos', { method: 'POST', headers: { 'X-Test': '1' } }),
  ).resolves.toEqual({ ok: true })
  expect(fetchMock).toHaveBeenCalledWith('/api/todos', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Test': '1' },
  })
})

it('returns undefined for 204 responses', async () => {
  fetchMock.mockResolvedValue(new Response(null, { status: 204 }))
  await expect(request('/todos/1')).resolves.toBeUndefined()
})

it('reports a connection problem when fetch fails', async () => {
  fetchMock.mockRejectedValue(new TypeError('network'))
  await expect(request('/todos')).rejects.toThrow(
    'Cannot connect to the server. Please try again.',
  )
})

it('rethrows the original error when the request was aborted', async () => {
  const controller = new AbortController()
  controller.abort()
  const abortError = new DOMException('Aborted', 'AbortError')
  fetchMock.mockRejectedValue(abortError)
  await expect(
    request('/todos', { signal: controller.signal }),
  ).rejects.toBe(abortError)
})

it('shows a validation message for 422 responses', async () => {
  fetchMock.mockResolvedValue(jsonResponse({ detail: [{ msg: 'bad' }] }, 422))
  await expect(request('/todos')).rejects.toThrow(/Check the task details/)
})

it('uses the string detail from error responses', async () => {
  fetchMock.mockResolvedValue(jsonResponse({ detail: 'Task not found' }, 404))
  await expect(request('/todos/9')).rejects.toThrow('Task not found')
})

it('falls back to a generic message when the error body is unusable', async () => {
  fetchMock.mockResolvedValue(new Response('<html>', { status: 500 }))
  await expect(request('/todos')).rejects.toThrow(
    'The operation failed. Please try again.',
  )
})
