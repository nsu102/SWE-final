// v2: stored shapes changed from the mock ids to real products; old keys are ignored.
export const HISTORY_KEY = "lookfind-history-v2", FAVORITES_KEY = "lookfind-favorites-v2";
export const MAX_HISTORY = 30;
export const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
export const sourceLabels: Record<string, string> = { musinsa: "MUSINSA", zigzag: "ZIGZAG", ably: "ABLY" };
