"use client";

import { useLookFind } from "../contexts/lookfind-context";
import { productKey } from "../utils/product";
import MemberGate from "./member-gate";
import SavedCard from "./saved-card";

export default function SavedView() {
  const { user, authLoading, favorites, toggleFavorite, openLogin } = useLookFind();
  if (authLoading) return <p className="api-status page-status">로그인 상태를 확인하고 있습니다…</p>;
  if (!user) return <MemberGate title="찜 목록은 로그인 후 이용할 수 있어요" text="마음에 드는 상품을 저장하고 나중에 비교해보세요." onLogin={openLogin} />;
  return <section className="collection-page">
    <div className="collection-heading"><h1>SAVED LOOKS</h1><span className="collection-count">{favorites.length} ITEMS</span></div>
    {favorites.length
      ? <div className="saved-grid">{favorites.map(item => <SavedCard key={productKey(item)} item={item} onRemove={toggleFavorite} />)}</div>
      : <p className="collection-empty">아직 저장한 제품이 없습니다.</p>}
  </section>;
}
