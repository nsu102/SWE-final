import type { User } from "../types/api";

/** Profile photo, or the first letter of the name/email when there is none. */
export default function UserAvatar({ user, src = user.avatar_url, className }: { user: User; src?: string | null; className: string }) {
  return <span className={className} aria-hidden="true">
    {src
      ? <img src={src} alt="" referrerPolicy="no-referrer" />
      : (user.display_name || user.email || "?").charAt(0).toUpperCase()}
  </span>;
}
