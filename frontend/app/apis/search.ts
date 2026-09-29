import { API } from "../constants/look-find";
import type { Product, SearchResponse } from "../types/look-find";

export const productKey = (item: Product) => `${item.platform}-${item.goods_no}`;
// The media route re-signs the S3 URL on every load, so saved/archived items never expire.
export const productImage = (item: Product) => `${API}/media/${item.platform}/${item.goods_no}`;
export const photoStyle = (url: string) => ({ background: `#fff url("${url}") center / contain no-repeat` });
export const won = (value: number | null) => value == null ? "가격 정보 없음" : `${new Intl.NumberFormat("ko-KR").format(value)}원`;

export async function searchImage(file: File): Promise<SearchResponse> {
  const body = new FormData();
  body.append("image", file);
  let response: Response;
  try {
    response = await fetch(`${API}/api/search?limit=24`, { method: "POST", body });
  } catch {
    throw new Error(`검색 서버(${API})에 연결할 수 없어요.`);
  }
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = typeof payload.detail === "string" ? payload.detail : "";
    throw new Error(`검색에 실패했어요 (${response.status}) ${detail}`.trim());
  }
  return payload;
}
