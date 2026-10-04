import { API_BASE, IDEMPOTENT_METHODS, NO_REFRESH_PATHS, RETRY_DELAYS_MS, RETRYABLE_STATUS } from "../constants/api";

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

const isAbort = (error: unknown) => error instanceof DOMException && error.name === "AbortError";

function sleep(ms: number, signal?: AbortSignal | null) {
  return new Promise<void>((resolve, reject) => {
    if (signal?.aborted) return reject(new DOMException("Aborted", "AbortError"));
    const timer = setTimeout(resolve, ms);
    signal?.addEventListener("abort", () => { clearTimeout(timer); reject(new DOMException("Aborted", "AbortError")); }, { once: true });
  });
}

async function errorDetail(response: Response) {
  const body = await response.json().catch(() => null);
  if (typeof body?.detail === "string") return body.detail;
  if (response.status === 422) return "이메일 형식과 비밀번호 길이(8~128자)를 확인해 주세요.";
  return "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
}

let refreshing: Promise<boolean> | null = null;

/**
 * Rotate the refresh token (HttpOnly cookie) for a new access token.
 * Concurrent 401s share one call: the server rotates the refresh token, so a second
 * parallel refresh would present an already-revoked token.
 */
export function refreshSession(): Promise<boolean> {
  refreshing ??= fetch(`${API_BASE}/auth/refresh`, { method: "POST", credentials: "same-origin", cache: "no-store" })
    .then(response => response.ok, () => false)
    .finally(() => { refreshing = null; });
  return refreshing;
}

/**
 * fetch + JSON with the auth/retry policy:
 * - 401 → refresh once and resend (safe for any method: the server rejected it before running it)
 * - network error / 502·503·504 → back off and retry, idempotent methods only
 */
export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const method = (options.method ?? "GET").toUpperCase();
  const retryable = IDEMPOTENT_METHODS.includes(method);
  let retries = 0;
  let refreshed = false;
  for (;;) {
    let response: Response;
    try {
      response = await fetch(`${API_BASE}${path}`, { ...options, credentials: "same-origin", cache: "no-store" });
    } catch (error) {
      if (isAbort(error)) throw error;
      if (retryable && retries < RETRY_DELAYS_MS.length) { await sleep(RETRY_DELAYS_MS[retries++], options.signal); continue; }
      throw new ApiError(0, "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
    }
    if (response.status === 401 && !refreshed && !NO_REFRESH_PATHS.includes(path)) {
      refreshed = true;
      if (await refreshSession()) continue;
    }
    if (retryable && RETRYABLE_STATUS.includes(response.status) && retries < RETRY_DELAYS_MS.length) {
      await sleep(RETRY_DELAYS_MS[retries++], options.signal);
      continue;
    }
    if (!response.ok) throw new ApiError(response.status, await errorDetail(response));
    return response.status === 204 ? undefined as T : response.json();
  }
}

export const jsonBody = (body: unknown, method = "POST"): RequestInit => ({
  method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
});
