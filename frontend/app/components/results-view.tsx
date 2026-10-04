"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useLookFind } from "../contexts/lookfind-context";
import { usePlatformFilter } from "../hooks/use-platform-filter";
import { productKey } from "../utils/product";
import PlatformFilter from "./platform-filter";
import ProductCard from "./product-card";

export default function ResultsView() {
  const { search, favorites, toggleFavorite, openHistory, retrySearch } = useLookFind();
  const { image, matches, status, searching, failed, canRetry } = search;
  const savedKeys = new Set(favorites.map(productKey));
  const { filter, activeIndex, changeFilter, cards, matchGridRef, headingVisible, onGridScroll } = usePlatformFilter(matches);

  // /results?history=<id> reopens an ARCHIVE entry (also on reload / shared link).
  const historyId = useSearchParams().get("history");
  useEffect(() => {
    if (historyId && historyId !== search.historyId) openHistory(historyId);
  }, [historyId, search.historyId, openHistory]);

  const emptyMessage = searching ? "검색 중…" : matches.length ? "이 플랫폼의 상품은 아직 없어요." : "사진을 업로드하면 비슷한 상품이 여기에 표시돼요.";
  return <section className="test-search">
    <div className="test-heading"><div><h1>SIMILAR LOOKS</h1></div></div>
    <div className="test-controls">
      <p className="test-control-label">YOUR PHOTO</p>
      <div className="matches-controls">
        <p className={`test-control-label matched-products-label ${headingVisible ? "" : "is-hidden"}`}>MATCHED PRODUCTS</p>
        <PlatformFilter filter={filter} activeIndex={activeIndex} onChange={changeFilter} />
      </div>
    </div>
    <div className="test-layout">
      <aside className="uploaded-column">
        <div className="uploaded-photo" style={{ backgroundImage: `url(${image ?? "/lookfind-hero.png"})` }} />
        <div>
          <small className={failed ? "search-error" : ""} aria-live="polite">{status || "사진을 올리면 상의 영역을 분석해 비슷한 상품을 찾아드려요."}</small>
          {failed && canRetry && <button className="inline-action retry-search" onClick={retrySearch}>다시 시도 ↻</button>}
        </div>
      </aside>
      <section className="matches-column">
        <div className="match-grid" ref={matchGridRef} onScroll={event => onGridScroll(event.currentTarget.scrollTop)}>
          {!cards.length && !failed && <p className="collection-empty" style={{ gridColumn: "1 / -1" }}>{emptyMessage}</p>}
          {cards.map(({ item, key, className, style, ref }) =>
            <ProductCard key={key} item={item} saved={savedKeys.has(productKey(item))} onFavorite={toggleFavorite} className={className} style={style} cardRef={ref} />)}
        </div>
      </section>
    </div>
  </section>;
}
