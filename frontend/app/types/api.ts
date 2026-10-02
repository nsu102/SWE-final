// Mirrors the backend models in backend/src/backend/app.py.
export type User = { id: string; email: string; display_name?: string | null; avatar_url?: string | null };
export type Product = {
  platform: string; goods_no: string; goods_name: string; brand_name: string;
  price: number | null; product_url: string; image_url: string; similarity: number;
};
export type SearchResponse = {
  query_id: string; used_top_mask: boolean; top_ratio: number; box_preview: string;
  masked_preview: string | null; elapsed_ms: number; results: Product[];
};
export type HistoryItem = { id: string; label: string; searched_at: string; count: number; image_url: string | null };
export type HistoryPage = { items: HistoryItem[]; next_cursor: number | null };
export type HistoryDetail = HistoryItem & { results: Product[] };
