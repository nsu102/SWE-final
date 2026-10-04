"use client";

import { useEffect, useState } from "react";
import { deleteHistory, getHistory, restoreHistory } from "../apis/history";
import { HISTORY_RESTORE_CHUNK } from "../constants/look-find";
import { errorMessage, isUnauthorized } from "../utils/error";
import ArchiveCard from "./archive-card";
import type { HistoryItem } from "../types/api";

export default function HistoryView({ onOpen, onLogin }: { onOpen: (id: string) => void; onLogin: () => void }) {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [cursor, setCursor] = useState<number | null>(null);
  const [undo, setUndo] = useState<string[]>([]);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState("");
  const [expired, setExpired] = useState(false);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    getHistory(undefined, controller.signal).then(data => { setItems(data.items); setCursor(data.next_cursor); setBusy(false); }).catch(error => {
      if (controller.signal.aborted) return;
      setError(errorMessage(error)); setExpired(isUnauthorized(error)); setBusy(false);
    });
    return () => controller.abort();
  }, [revision]);
  async function act(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true); setError("");
    try { await action(); } catch (error) { setError(errorMessage(error)); setExpired(isUnauthorized(error)); }
    finally { setBusy(false); }
  }
  async function remove(id?: string) {
    const data = await deleteHistory(id);
    setUndo(data.deleted_ids);
    const page = await getHistory(); setItems(page.items); setCursor(page.next_cursor);
  }
  return <section className="collection-page" aria-busy={busy}>
    <div className="collection-heading"><h1>ARCHIVE</h1><div className="collection-actions">
      <button className="collection-action" disabled={busy || !items.length} onClick={() => void act(() => remove())}>CLEAR ALL ↗</button>
      <button className="collection-return" disabled={busy || !undo.length} onClick={() => void act(async () => {
        for (let start = 0; start < undo.length; start += HISTORY_RESTORE_CHUNK) await restoreHistory(undo.slice(start, start + HISTORY_RESTORE_CHUNK));
        setUndo([]); const page = await getHistory(); setItems(page.items); setCursor(page.next_cursor);
      })}>RETURN ↶</button>
    </div></div>
    {undo.length > 0 && <p className="api-status">삭제한 기록은 10분 이내 RETURN으로 복원할 수 있어요.</p>}
    {error && <div className="api-error" role="alert">{error} <button className="inline-action" onClick={expired ? onLogin : () => { setError(""); setBusy(true); setRevision(value => value + 1); }}>{expired ? "로그인" : "다시 시도"}</button></div>}
    {busy && <p role="status">기록을 불러오고 있습니다…</p>}
    {!busy && !items.length && !error && <p className="collection-empty">저장된 검색 이력이 없습니다. 사진을 검색하면 여기에 저장됩니다.</p>}
    <div className="archive-grid">{items.map(item => <ArchiveCard key={item.id} item={item} busy={busy} onOpen={onOpen} onRemove={id => void act(() => remove(id))} />)}</div>
    {cursor && <button className="inline-action load-more" disabled={busy} onClick={() => void act(async () => {
      const page = await getHistory(cursor); setItems(current => [...current, ...page.items]); setCursor(page.next_cursor);
    })}>더 보기 ↓</button>}
  </section>;
}
