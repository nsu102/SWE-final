import type { Product } from "../types/api";

export const productKey = (item: Product) => `${item.platform}-${item.goods_no}`;
// The media route re-signs the S3 URL on every load, so saved/archived items never expire.
export const productImage = (item: Product) => `/media/${item.platform}/${item.goods_no}`;
export const photoStyle = (url: string) => ({ background: `#fff url("${url}") center / contain no-repeat` });
