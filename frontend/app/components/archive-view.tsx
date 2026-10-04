"use client";

import { useRouter } from "next/navigation";
import HistoryView from "./history-view";
import { useLookFind } from "../contexts/lookfind-context";
import MemberGate from "./member-gate";

export default function ArchiveView() {
  const router = useRouter();
  const { user, authLoading, openLogin } = useLookFind();
  if (authLoading) return <p className="api-status page-status">로그인 상태를 확인하고 있습니다…</p>;
  if (!user) return <MemberGate title="검색 기록은 로그인 후 저장돼요." text="이전에 검색한 사진과 결과를 다시 확인할 수 있어요." onLogin={openLogin} />;
  return <HistoryView key={user.id} onLogin={openLogin} onOpen={id => router.push(`/results?history=${id}`)} />;
}
