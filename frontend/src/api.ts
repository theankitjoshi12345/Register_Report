import { flattenErrors } from './report'
import type { FieldErrors } from './report'

const runtimeEnv = (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env ?? {}
const configuredApiBase = (runtimeEnv.VITE_API_BASE_URL ?? '').replace(/\/+$/, '')

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
    const target = /^https?:\/\//.test(url) ? url : `${configuredApiBase}${url}`
    response = await fetch(target, { credentials: configuredApiBase ? 'include' : 'same-origin', ...options })
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
