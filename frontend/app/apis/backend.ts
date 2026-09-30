import { API, TOKEN_KEY } from "../constants/look-find";
import type { Product, SearchHistory, SearchResponse } from "../types/look-find";

export const productKey = (item: Product) => `${item.platform}-${item.goods_no}`;
// The media route re-signs the S3 URL on every load, so saved/archived items never expire.
export const productImage = (item: Product) => `${API}/media/${item.platform}/${item.goods_no}`;
export const photoStyle = (url: string) => ({ background: `#fff url("${url}") center / contain no-repeat` });
export const won = (value: number | null) => value == null ? "가격 정보 없음" : `${new Intl.NumberFormat("ko-KR").format(value)}원`;
export const formatDate = (iso: string) => new Date(iso).toLocaleString("ko-KR", { month: "long", day: "numeric", hour: "numeric", minute: "2-digit" });

// Session token (opaque, server-side session). Storage can be blocked, so failures mean "logged out".
export const readToken = () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } };
export const writeToken = (token: string | null) => { try { if (token) localStorage.setItem(TOKEN_KEY, token); else localStorage.removeItem(TOKEN_KEY); } catch {} };

/** The stored session was rejected (expired or logged out elsewhere). */
export class AuthError extends Error {}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const token = readToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (typeof init.body === "string") headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(`${API}${path}`, { ...init, headers });
  } catch {
    throw new Error(`서버(${API})에 연결할 수 없어요.`);
  }
  if (response.status === 204) return undefined as T;
  const payload = await response.json().catch(() => ({}));
  const detail = typeof payload.detail === "string" ? payload.detail : "";
  if (response.status === 401 && token) {
    writeToken(null);
    throw new AuthError("로그인이 만료됐어요. 다시 로그인해 주세요.");
  }
  if (!response.ok) throw new Error(detail || `요청에 실패했어요 (${response.status})`);
  return payload as T;
}

export function searchImage(file: File, label: string) {
  const body = new FormData();
  body.append("image", file);
  body.append("label", label);
  return request<SearchResponse>("/api/search?limit=24", { method: "POST", body });
}

export const authenticate = (mode: "login" | "signup", email: string, password: string) =>
  request<{ token: string; email: string }>(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify({ email, password }) });
export const logout = () => request<void>("/api/auth/logout", { method: "POST" });
export const fetchMe = () => request<{ email: string }>("/api/auth/me");

export const fetchHistory = () => request<SearchHistory[]>("/api/history");
export const fetchHistoryResults = (id: number) => request<Product[]>(`/api/history/${id}`);
export const removeHistory = (id: number) => request<void>(`/api/history/${id}`, { method: "DELETE" });
export const clearHistory = () => request<void>("/api/history", { method: "DELETE" });
export const restoreHistory = () => request<void>("/api/history/restore", { method: "POST" });

export const fetchFavorites = () => request<Product[]>("/api/favorites");
export const saveFavorite = (item: Product, saved: boolean) =>
  request<void>(`/api/favorites/${item.platform}/${item.goods_no}`, { method: saved ? "PUT" : "DELETE" });
