import type { Product } from "../types/api";
import { request } from "./http";

export const getFavorites = () => request<Product[]>("/favorites");
export const saveFavorite = (item: Product, saved: boolean) =>
  request<void>(`/favorites/${item.platform}/${item.goods_no}`, { method: saved ? "PUT" : "DELETE" });
