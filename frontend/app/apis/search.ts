import { SEARCH_LIMIT } from "../constants/api";
import type { SearchResponse } from "../types/api";
import { request } from "./http";

export const searchImage = (file: File, label: string, signal?: AbortSignal) => {
  const form = new FormData();
  form.append("image", file);
  form.append("label", label);
  return request<SearchResponse>(`/search?limit=${SEARCH_LIMIT}`, { method: "POST", body: form, signal });
};
