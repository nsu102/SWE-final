export const sourceLabels: Record<string, string> = { musinsa: "MUSINSA", zigzag: "ZIGZAG", ably: "ABLY" };
export const LOADING_MESSAGE = "상의 영역을 찾고 비슷한 상품을 검색하고 있어요. 첫 검색은 모델 로딩 때문에 오래 걸릴 수 있어요.";
// Original photo limit; uploads are downscaled to UPLOAD_MAX_SIDE before sending.
export const MAX_INPUT_BYTES = 20 * 1024 * 1024;
export const UPLOAD_MAX_SIDE = 1600;
export const NAV_ITEMS = [["/", "SEARCH"], ["/archive", "ARCHIVE"], ["/saved", "SAVED"], ["/results", "RESULTS"]] as const;
export const PLATFORM_FILTERS = [{ id: "all", label: "ALL" }, { id: "musinsa", label: "MUSINSA" }, { id: "zigzag", label: "ZIGZAG" }, { id: "ably", label: "ABLY" }] as const;
// Card motion when switching platform filters (ms).
export const FILTER_SWAP_DELAY = 170;
export const FILTER_COLLAPSE_DELAY = 180;
export const FILTER_SWAP_SETTLE = 560;
export const CARD_FLIP_DURATION = 420;
export const GRID_SCROLL_RESET = 260;
export const CARD_STAGGER = 65;
export const HISTORY_RESTORE_CHUNK = 1000; // backend accepts at most this many ids per restore call
// MY PAGE profile editing (backend: routes/account.py).
export const PROFILE_NAME_MAX = 30;
export const AVATAR_UPLOAD_SIDE = 512; // the server crops to a 256px square
