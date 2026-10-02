import type { HistoryDetail, HistoryPage, Product, SearchResponse, User } from "../types/api";

export const productKey = (item: Product) => `${item.platform}-${item.goods_no}`;
// The media route re-signs the S3 URL on every load, so saved/archived items never expire.
export const productImage = (item: Product) => `/media/${item.platform}/${item.goods_no}`;
export const photoStyle = (url: string) => ({ background: `#fff url("${url}") center / contain no-repeat` });
export const won = (value: number | null) => value == null ? "가격 정보 없음" : `${new Intl.NumberFormat("ko-KR").format(value)}원`;

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

// Same-origin calls (next.config.ts proxies /api to the backend); the session is an HttpOnly cookie.
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api${path}`, { ...options, credentials: "same-origin", cache: "no-store" });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError(0, "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail
      : response.status === 422 ? "이메일 형식과 비밀번호 길이(8~128자)를 확인해 주세요."
      : "요청을 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.";
    throw new ApiError(response.status, detail);
  }
  return response.status === 204 ? undefined as T : response.json();
}
const json = (body: unknown, method = "POST"): RequestInit => ({ method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const getMe = (signal?: AbortSignal) => request<User>("/auth/me", { signal });
export const signIn = (email: string, password: string) => request<User>("/auth/login", json({ email, password }));
export const signUp = (email: string, password: string) => request<User>("/auth/register", json({ email, password }));
export const signOut = () => request<void>("/auth/logout", { method: "POST" });
export const requestPasswordReset = (email: string) => request<void>("/auth/reset-request", json({ email }));
export const resetPassword = (token: string, password: string) => request<User>("/auth/reset", json({ token, password }));

export const getHistory = (before?: number, signal?: AbortSignal) => request<HistoryPage>(`/history${before ? `?before=${before}` : ""}`, { signal });
export const getHistoryDetail = (id: string) => request<HistoryDetail>(`/history/${id}`);
export const deleteHistory = (id?: string) => request<{ deleted_ids: string[] }>(`/history${id ? `/${id}` : ""}`, { method: "DELETE" });
export const restoreHistory = (ids: string[]) => request<{ restored: number }>("/history/restore", json({ ids }));

export const searchImage = (file: File, label: string, signal?: AbortSignal) => {
  const form = new FormData();
  form.append("image", file);
  form.append("label", label);
  return request<SearchResponse>("/search?limit=24", { method: "POST", body: form, signal });
};

export const getFavorites = () => request<Product[]>("/favorites");
export const saveFavorite = (item: Product, saved: boolean) =>
  request<void>(`/favorites/${item.platform}/${item.goods_no}`, { method: saved ? "PUT" : "DELETE" });

export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
