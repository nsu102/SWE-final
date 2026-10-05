"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLookFind } from "../contexts/lookfind-context";
import MemberGate from "./member-gate";
import MyPage from "./my-page";
import ProfileEditModal from "./profile-edit-modal";

export default function MyPageView() {
  const router = useRouter();
  const { user, authLoading, openLogin, logout, updateUser, setNotice } = useLookFind();
  const [editing, setEditing] = useState(false);
  if (!user) return authLoading ? <p className="api-status page-status">로그인 상태를 확인하고 있습니다…</p>
    : <MemberGate title="로그인이 필요해요." text="로그인 후 내 계정을 확인할 수 있어요." onLogin={openLogin} />;
  return <>
    <MyPage user={user} busy={authLoading} onHistory={() => router.push("/archive")} onSaved={() => router.push("/saved")} onLogout={() => void logout()} onEdit={() => setEditing(true)} />
    {editing && <ProfileEditModal user={user} onClose={() => setEditing(false)} onSaved={next => { updateUser(next); setEditing(false); setNotice("프로필을 저장했어요."); }} />}
  </>;
}
