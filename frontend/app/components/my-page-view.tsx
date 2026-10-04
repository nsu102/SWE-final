"use client";

import { useRouter } from "next/navigation";
import { useLookFind } from "../contexts/lookfind-context";
import MemberGate from "./member-gate";
import MyPage from "./my-page";

export default function MyPageView() {
  const router = useRouter();
  const { user, authLoading, openLogin, logout } = useLookFind();
  if (!user) return authLoading ? <p className="api-status page-status">로그인 상태를 확인하고 있습니다…</p>
    : <MemberGate title="로그인이 필요해요." text="로그인 후 내 계정을 확인할 수 있어요." onLogin={openLogin} />;
  return <MyPage user={user} busy={authLoading} onHistory={() => router.push("/archive")} onSaved={() => router.push("/saved")} onLogout={() => void logout()} />;
}
