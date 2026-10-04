import type { HistoryDetail, HistoryPage } from "../types/api";
import { jsonBody, request } from "./http";

export const getHistory = (before?: number, signal?: AbortSignal) => request<HistoryPage>(`/history${before ? `?before=${before}` : ""}`, { signal });
export const getHistoryDetail = (id: string, signal?: AbortSignal) => request<HistoryDetail>(`/history/${id}`, { signal });
export const deleteHistory = (id?: string) => request<{ deleted_ids: string[] }>(`/history${id ? `/${id}` : ""}`, { method: "DELETE" });
export const restoreHistory = (ids: string[]) => request<{ restored: number }>("/history/restore", jsonBody({ ids }));
