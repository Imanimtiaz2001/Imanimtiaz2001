export class ApiError extends Error {
  code: string;
  traceId?: string;
  constructor(message: string, code: string, traceId?: string) {
    super(message);
    this.code = code;
    this.traceId = traceId;
  }
}
export async function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin' });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new ApiError(
      data?.error?.message || `Request failed (${response.status}).`,
      data?.error?.code || 'request_failed',
      data?.error?.trace_id,
    );
  }
  return response.status === 204 ? (undefined as T) : (response.json() as Promise<T>);
}
