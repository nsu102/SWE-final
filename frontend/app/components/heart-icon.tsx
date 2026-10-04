export default function HeartIcon({ filled = false }: { filled?: boolean }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 20.8-1.32-1.2C5.48 14.9 2.4 12.1 2.4 8.58c0-2.88 2.26-5.18 5.13-5.18 1.62 0 3.18.75 4.2 1.96a5.53 5.53 0 0 1 4.2-1.96c2.87 0 5.13 2.3 5.13 5.18 0 3.52-3.08 6.32-8.28 11.02L12 20.8Z" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={filled ? "1" : "1.15"} strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
