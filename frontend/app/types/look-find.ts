// Mirrors the backend SearchResult / SearchResponse models (backend/src/backend/app.py).
export type Product = { platform: string; goods_no: string; goods_name: string; brand_name: string; price: number | null; product_url: string; image_url: string; similarity: number };
export type SearchResponse = { used_top_mask: boolean; top_ratio: number; box_preview: string; masked_preview: string | null; elapsed_ms: number; results: Product[] };
export type SearchHistory = { id: string; label: string; searchedAt: string; count: number; thumb: string; results: Product[] };
