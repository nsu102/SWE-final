"use client";

import { useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useLookFind } from "../contexts/lookfind-context";

export default function HomeHero() {
  const { openUpload, overlayOpen } = useLookFind();
  const [analysisStage, setAnalysisStage] = useState(0);
  const stageLock = useRef(false);
  const touchStart = useRef(0);

  // Wheel/swipe steps the garment-analysis callouts (TOP → PANTS → BOOTS) instead of scrolling.
  useEffect(() => {
    if (overlayOpen) return;

    const changeStage = (direction: number) => {
      if (stageLock.current) return;
      setAnalysisStage((current) => {
        const next = Math.max(0, Math.min(2, current + direction));
        if (next === current) return current;
        stageLock.current = true;
        window.setTimeout(() => { stageLock.current = false; }, 750);
        return next;
      });
    };
    const onWheel = (event: WheelEvent) => {
      if (Math.abs(event.deltaY) < 12) return;
      event.preventDefault();
      changeStage(event.deltaY > 0 ? 1 : -1);
    };
    const onTouchStart = (event: TouchEvent) => { touchStart.current = event.touches[0]?.clientY ?? 0; };
    const onTouchEnd = (event: TouchEvent) => {
      const distance = touchStart.current - (event.changedTouches[0]?.clientY ?? 0);
      if (Math.abs(distance) > 35) changeStage(distance > 0 ? 1 : -1);
    };
    window.addEventListener("wheel", onWheel, { passive: false });
    window.addEventListener("touchstart", onTouchStart, { passive: true });
    window.addEventListener("touchend", onTouchEnd, { passive: true });
    return () => { window.removeEventListener("wheel", onWheel); window.removeEventListener("touchstart", onTouchStart); window.removeEventListener("touchend", onTouchEnd); };
  }, [overlayOpen]);


  return <section className="home">
    <section className="hero">
      <div className="hero-copy">
        <h1>LOOKFIND</h1>
        <p>사진 한 장으로 원하는 스타일을 찾아보세요.<br />사진 속 옷을 AI가 하나씩 분석하고,<br />비슷한 디자인의 상품을 찾아드립니다.<br />무신사, 지그재그, 에이블리의 상품을 한눈에 비교하고<br />당신이 찾던 옷을 가장 쉽게 발견해보세요.</p>
        <button className="photo-action" onClick={openUpload}>PHOTO UPLOAD <span>↗</span></button>
      </div>
      <div className="hero-image"><Image src="/lookfind-hero.png" alt="LookFind 스타일 이미지" fill priority sizes="(max-width: 700px) 100vw, 50vw" /><div className={`analysis-layer stage-${analysisStage}`} aria-label="AI 의류 분석 표시"><div className="analysis-box shirt"><span>TOP</span><div className="analysis-crop crop-shirt"><small>TOP</small></div></div><div className="analysis-box pants"><span>PANTS</span><div className="analysis-crop crop-pants"><small>PANTS</small></div></div><div className="analysis-box boots"><span>BOOTS</span><div className="analysis-crop crop-boots"><small>BOOTS</small></div></div></div></div>
    </section>
  </section>;
}
