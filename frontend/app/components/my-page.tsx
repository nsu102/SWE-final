"use client";

import type { User } from "../types/api";

type MyPageProps = {
  user: User;
  busy: boolean;
  onHistory: () => void;
  onSaved: () => void;
  onLogout: () => void;
};

export default function MyPage({ user, busy, onHistory, onSaved, onLogout }: MyPageProps) {
  return <section className="my-page">
    <div className="my-page-heading"><h1>MY PAGE</h1></div>
    <div className="my-page-layout">
      <section className="my-profile" aria-labelledby="my-profile-title">
        <div className="my-profile-avatar" aria-hidden="true">{user.email.charAt(0).toUpperCase()}</div>
        <h2 id="my-profile-title">내 계정</h2>
        <dl><dt>EMAIL</dt><dd>{user.email}</dd></dl>
        <button className="photo-action" disabled={busy} onClick={onLogout}>{busy ? "처리 중…" : "LOGOUT"}<span aria-hidden="true">↗</span></button>
      </section>
      <div className="my-page-links">
        <button className="my-page-link" onClick={onHistory}><span className="my-page-link-label">ARCHIVE</span><strong>검색 기록</strong><span>이전에 검색한 사진과 결과를 다시 확인하세요.</span><span className="my-page-link-arrow" aria-hidden="true">↗</span></button>
        <button className="my-page-link" onClick={onSaved}><span className="my-page-link-label">SAVED</span><strong>좋아요 목록</strong><span>마음에 드는 상품을 모아 보고 비교하세요.</span><span className="my-page-link-arrow" aria-hidden="true">↗</span></button>
      </div>
    </div>
  </section>;
}
