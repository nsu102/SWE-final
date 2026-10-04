"use client";

import { sourceLabels } from "../constants/look-find";
import type { Product } from "../types/api";
import { won } from "../utils/format";
import { photoStyle, productImage } from "../utils/product";
import HeartIcon from "./heart-icon";

export default function SavedCard({ item, onRemove }: { item: Product; onRemove: (item: Product) => void }) {
  return <article className="saved-card">
    <a className="match-link" href={item.product_url} target="_blank" rel="noopener noreferrer">
      <div className="saved-visual has-photo" style={photoStyle(productImage(item))}><span>{sourceLabels[item.platform] ?? item.platform}</span></div>
      <h2 title={item.goods_name}>{item.goods_name}</h2>
    </a>
    <div className="saved-product-line">
      <p>{item.brand_name}</p>
      <button className="saved-favorite" aria-label={`${item.goods_name} 저장 취소`} onClick={() => onRemove(item)}><HeartIcon filled /></button>
    </div>
    <strong>{won(item.price)}</strong>
  </article>;
}
