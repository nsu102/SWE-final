"use client";

import type { User } from "../types/api";
import UserAvatar from "./user-avatar";

type MyPageProps = {
  user: User;
  busy: boolean;
  onHistory: () => void;
  onSaved: () => void;
  onLogout: () => void;
  onEdit: () => void;
};

export default function MyPage({ user, busy, onHistory, onSaved, onLogout, onEdit }: MyPageProps) {
  return <section className="my-page">
    <div className="my-page-heading"><h1>MY PAGE</h1></div>
    <div className="my-page-layout">
      <section className="my-profile" aria-labelledby="my-profile-title">
        <div className="my-profile-top">
          <UserAvatar user={user} className="my-profile-avatar" />
          <button className="my-profile-edit" onClick={onEdit}>프로필 수정 <span aria-hidden="true">✎</span></button>
        </div>
        <h2 id="my-profile-title">{user.display_name || "내 계정"}</h2>
        <dl>{user.display_name && <><dt>NAME</dt><dd>{user.display_name}</dd></>}{user.email && <><dt>EMAIL</dt><dd>{user.email}</dd></>}</dl>
        <button className="photo-action" disabled={busy} onClick={onLogout}>{busy ? "처리 중…" : "LOGOUT"}<span aria-hidden="true">↗</span></button>
      </section>
      <div className="my-page-links">
        <button className="my-page-link" onClick={onHistory}><span className="my-page-link-label">ARCHIVE</span><strong>검색 기록</strong><span>이전에 검색한 사진과 결과를 다시 확인하세요.</span><span className="my-page-link-arrow" aria-hidden="true">↗</span></button>
        <button className="my-page-link" onClick={onSaved}><span className="my-page-link-label">SAVED</span><strong>좋아요 목록</strong><span>마음에 드는 상품을 모아 보고 비교하세요.</span><span className="my-page-link-arrow" aria-hidden="true">↗</span></button>
      </div>
    </div>
  </section>;
}
