import { flattenErrors } from './report'
import type { FieldErrors } from './report'

export class ApiError extends Error {
  status: number
  errors: FieldErrors
  constructor(message: string, status = 0, errors: FieldErrors = {}) {
    super(message)
    this.status = status
    this.errors = errors
  }
}

export async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, { credentials: 'same-origin', ...options })
  } catch {
    throw new ApiError('The report service is unavailable. Check your connection and try again.')
  }
  let data: unknown
  try { data = await response.json() } catch {
    throw new ApiError('The report service returned an unreadable response. Please try again.', response.status)
  }
  if (!response.ok) {
    const body = data && typeof data === 'object' ? data as Record<string, unknown> : {}
    const errors = flattenErrors(body.errors)
    const message = typeof body.error === 'string' ? body.error : typeof body.detail === 'string' ? body.detail
      : typeof body.errors === 'string' ? body.errors : errors.form ? errors.form
      : Object.keys(errors).length ? 'Please correct the highlighted entries.'
        : response.status >= 500 ? 'The report service could not complete this request. Please try again.' : 'The request could not be completed.'
    throw new ApiError(message, response.status, errors)
  }
  return data as T
}
