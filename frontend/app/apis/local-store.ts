import { FAVORITES_KEY, HISTORY_KEY } from "../constants/look-find";
import type { Product, SearchHistory } from "../types/look-find";
const get = (key: string, fallback: unknown) => { try { return JSON.parse(localStorage.getItem(key) ?? "null") ?? fallback; } catch { return fallback; } };
// Quota errors only lose persistence; the in-memory state stays correct.
const set = (key: string, value: unknown) => { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} };
export const readHistory = () => typeof window === "undefined" ? [] : get(HISTORY_KEY, []) as SearchHistory[];
export const writeHistory = (value: SearchHistory[]) => set(HISTORY_KEY, value);
export const readFavorites = () => typeof window === "undefined" ? [] : get(FAVORITES_KEY, []) as Product[];
export const writeFavorites = (value: Product[]) => set(FAVORITES_KEY, value);
