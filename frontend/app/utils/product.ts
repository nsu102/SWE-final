import type { Product } from "../types/api";

export const productKey = (item: Product) => `${item.platform}-${item.goods_no}`;
// Search, saved, and archive APIs return a freshly signed S3 URL. Using it directly avoids
// fanning a result grid out into one Lambda invocation per thumbnail; keep the media route as
// a fallback for legacy rows that do not have an object URL.
export const productImage = (item: Product) => item.image_url || `/media/${item.platform}/${item.goods_no}`;
export const photoStyle = (url: string) => ({ background: `#fff url("${url}") center / contain no-repeat` });
