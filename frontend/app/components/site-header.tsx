"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_ITEMS } from "../constants/look-find";
import { useLookFind } from "../contexts/lookfind-context";

export default function SiteHeader({ mode }: { mode: "login" | "upload" | null }) {
  const pathname = usePathname();
  const { user, authLoading, openLogin, logout, closeOverlays } = useLookFind();
  const items = user ? [...NAV_ITEMS, ["/mypage", "MY PAGE"] as const] : NAV_ITEMS;
  const name = user ? user.display_name || user.email.split("@")[0] : "";
  return <header className={mode ? `site-header ${mode}-active` : "site-header"}>
    <Link className="wordmark" href="/" onClick={closeOverlays}>LOOK<span>•</span>FIND</Link>
    <nav aria-label="주 메뉴">
      {items.map(([href, label]) => {
        const active = !mode && pathname === href;
        return <Link key={href} href={href} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={closeOverlays}>{label}</Link>;
      })}
    </nav>
    {user ? <div className="account-menu">
      <button className="account account-profile" title={user.email} aria-haspopup="menu">
        {user.avatar_url ? <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" /> : <span className="account-avatar-fallback">{(user.display_name || user.email).slice(0, 1).toUpperCase()}</span>}
        <span>{name}</span><i>⌄</i>
      </button>
      <div className="account-popover" role="menu">
        <div className="account-popover-head"><strong>{name}</strong>{user.email && <span>{user.email}</span>}</div>
        {/* blur so :focus-within doesn't keep the menu open after navigating */}
        <Link role="menuitem" href="/mypage" onClick={event => { event.currentTarget.blur(); closeOverlays(); }}>MY PAGE <span aria-hidden="true">↗</span></Link>
        <button role="menuitem" onClick={event => { event.currentTarget.blur(); void logout(); }}>LOGOUT <span aria-hidden="true">↗</span></button>
      </div>
    </div> : <button className="account" disabled={authLoading} onClick={openLogin}>{authLoading ? "LOADING…" : "LOGIN"}</button>}
  </header>;
}
