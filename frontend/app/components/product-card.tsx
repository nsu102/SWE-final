"use client";

import type { CSSProperties } from "react";
import { sourceLabels } from "../constants/look-find";
import type { Product } from "../types/api";
import { similarityPercent, won } from "../utils/format";
import { photoStyle, productImage } from "../utils/product";
import HeartIcon from "./heart-icon";

type Props = {
  item: Product; saved: boolean; onFavorite: (item: Product) => void;
  className?: string; style?: CSSProperties; cardRef?: (element: HTMLElement | null) => void;
};

/** A search result: photo, platform · similarity, name, brand, heart, price. */
export default function ProductCard({ item, saved, onFavorite, className = "match-card", style, cardRef }: Props) {
  return <article className={className} style={style} ref={cardRef}>
    <a className="match-link" href={item.product_url} target="_blank" rel="noopener noreferrer">
      <div className="match-photo has-photo" style={photoStyle(productImage(item))}><span>{sourceLabels[item.platform] ?? item.platform} · {similarityPercent(item.similarity)}</span></div>
      <h3 title={item.goods_name}>{item.goods_name}</h3>
    </a>
    <div className="match-product-line">
      <small>{item.brand_name}</small>
      <button className={saved ? "match-favorite saved" : "match-favorite"} onClick={() => onFavorite(item)} aria-label={`${item.goods_name} ${saved ? "저장 취소" : "저장"}`}><HeartIcon filled={saved} /></button>
    </div>
    <strong>{won(item.price)}</strong>
  </article>;
}
