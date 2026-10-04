"use client";

import { PLATFORM_FILTERS } from "../constants/look-find";

export default function PlatformFilter({ filter, activeIndex, onChange }: { filter: string; activeIndex: number; onChange: (id: string) => void }) {
  return <nav className="source-filter" aria-label="플랫폼 필터">
    <span className={`filter-indicator at-${activeIndex}`} aria-hidden="true" />
    {PLATFORM_FILTERS.map(({ id, label }) => <button className={filter === id ? "active" : ""} key={id} onClick={() => onChange(id)}>{label}</button>)}
  </nav>;
}
