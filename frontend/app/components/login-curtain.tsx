"use client";

import { ReactNode, useEffect, useRef, useState } from "react";

export default function LoginCurtain({ children, onClose }: { children: ReactNode; onClose: () => void }) {
  const curtain = useRef<HTMLElement>(null);
  const closeAnimation = useRef<Animation | null>(null);
  const [closing, setClosing] = useState(false);

  function closeCurtain() {
    if (closing || closeAnimation.current) return;
    const panel = curtain.current;
    if (!panel || window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      onClose();
      return;
    }

    // Start from the visible edge even if X is pressed while the curtain opens.
    const currentClip = getComputedStyle(panel).clipPath;
    setClosing(true);
    const animation = panel.animate(
      [{ clipPath: currentClip }, { clipPath: "inset(0 0 100% 0)" }],
      { duration: 1000, easing: "cubic-bezier(.22, 1, .36, 1)", fill: "forwards" },
    );
    closeAnimation.current = animation;
    animation.onfinish = onClose;
  }

  useEffect(() => {
    const previousFocus = document.activeElement;
    const previousOverflow = document.body.style.overflow;
    const panel = curtain.current;
    document.body.style.overflow = "hidden";
    panel?.focus({ preventScroll: true });
    return () => {
      closeAnimation.current?.cancel();
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected
          && (panel?.contains(document.activeElement) || document.activeElement === document.body)) {
        previousFocus.focus({ preventScroll: true });
      }
    };
  }, []);

  return <section className="login-curtain" ref={curtain} tabIndex={-1} aria-label="로그인" inert={closing}
    onKeyDown={event => { if (event.key === "Escape") { event.stopPropagation(); closeCurtain(); } }}>
    <button className="login-curtain-close" aria-label="로그인 화면 닫기" onClick={closeCurtain}>×</button>
    {children}
  </section>;
}
