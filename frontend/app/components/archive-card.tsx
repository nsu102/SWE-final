"use client";

import type { HistoryItem } from "../types/api";
import { dateTime } from "../utils/format";

type Props = { item: HistoryItem; busy: boolean; onOpen: (id: string) => void; onRemove: (id: string) => void };

export default function ArchiveCard({ item, busy, onOpen, onRemove }: Props) {
  return <article className="archive-card real-archive-card">
    <button className="archive-open" disabled={busy} onClick={() => onOpen(item.id)}>
      <div className="real-archive-image">{item.image_url && <img src={item.image_url} alt={item.label} />}</div>
      <div className="archive-info"><h2>{item.label}</h2><p>{dateTime(item.searched_at)}</p><strong>{item.count} MATCHES</strong></div>
    </button>
    <button className="archive-remove" aria-label={`${item.label} 삭제`} disabled={busy} onClick={() => onRemove(item.id)}>×</button>
  </article>;
}
