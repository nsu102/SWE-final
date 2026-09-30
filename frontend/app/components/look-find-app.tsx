"use client";

import { ChangeEvent, DragEvent, FormEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import Image from "next/image";
import * as backend from "../apis/backend";
import { AuthError, formatDate, photoStyle, productImage, productKey, readToken, won, writeToken } from "../apis/backend";
import { sourceLabels } from "../constants/look-find";
import type { Product, SearchHistory } from "../types/look-find";

type Page = "home" | "history" | "favorites" | "results" | "login";

const LOADING_MESSAGE = "상의 영역을 찾고 비슷한 상품을 검색하고 있어요. 첫 검색은 모델 로딩 때문에 오래 걸릴 수 있어요.";

export default function LookFindApp() {
  const [page, setPage] = useState<Page>("home");
  const [user, setUser] = useState<string | null>(null);
  const loggedIn = user !== null;
  const [history, setHistory] = useState<SearchHistory[]>([]);
  const [canRestore, setCanRestore] = useState(false);
  const [favorites, setFavorites] = useState<Product[]>([]);
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [uploadMode, setUploadMode] = useState(false);
  const [isClosingUpload, setIsClosingUpload] = useState(false);
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState("all");
  const [analysisStage, setAnalysisStage] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [matches, setMatches] = useState<Product[]>([]);
  const [searchStatus, setSearchStatus] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  const [stream, setStream] = useState<MediaStream>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const stageLock = useRef(false);
  const touchStart = useRef(0);

  useEffect(() => {
    if (page !== "home" || uploadMode) return;

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
  }, [page, uploadMode]);

  // Restore the server session on load, then load this account's archive and saved items.
  useEffect(() => {
    // Password reset links look like /?reset=<token>; open the login panel in reset mode.
    const token = new URLSearchParams(window.location.search).get("reset");
    if (token) {
      setResetToken(token); // eslint-disable-line react-hooks/set-state-in-effect
      setPage("login");
      window.history.replaceState(null, "", window.location.pathname);
    }
    if (readToken()) backend.fetchMe().then((me) => setUser(me.email), (error) => { if (error instanceof AuthError) setUser(null); });
  }, []);
  useEffect(() => {
    if (!user) return;
    backend.fetchHistory().then(setHistory, fail);
    backend.fetchFavorites().then(setFavorites, fail);
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  function signOutLocally() {
    writeToken(null);
    setUser(null);
    setHistory([]);
    setFavorites([]);
    setCanRestore(false);
  }

  function fail(error: unknown) {
    if (error instanceof AuthError) signOutLocally();
    window.alert((error as Error).message);
  }

  const refreshHistory = () => backend.fetchHistory().then(setHistory, fail);

  // Attach the live camera to <video>; stopping tracks here also covers cancel/capture/close.
  useEffect(() => {
    if (!stream) return;
    videoRef.current!.srcObject = stream;
    return () => stream.getTracks().forEach((track) => track.stop());
  }, [stream]);

  function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    loadImage(event.target.files?.[0]);
    event.target.value = "";
  }

  async function loadImage(file?: File, label = file?.name ?? "업로드 사진") {
    if (!file || searching) return;
    if (uploadedImage) URL.revokeObjectURL(uploadedImage);
    setStream(undefined);
    setUploadedImage(URL.createObjectURL(file));
    setUploadMode(false);
    setIsDragging(false);
    setPage("results");
    setMatches([]);
    setSearchFailed(false);
    setSearchStatus(LOADING_MESSAGE);
    setSearching(true);
    try {
      const data = await backend.searchImage(file, label);
      setMatches(data.results);
      setSearchStatus([
        data.used_top_mask ? `상의 비율 ${(data.top_ratio * 100).toFixed(1)}%` : "상의를 찾지 못해 사진 전체로 검색했어요",
        `${(data.elapsed_ms / 1000).toFixed(1)}초`,
        `${data.results.length}개 결과`,
        loggedIn ? "ARCHIVE에 저장됨" : "로그인하면 검색 기록이 저장돼요",
      ].join(" · "));
      if (loggedIn) refreshHistory();
    } catch (error) {
      if (error instanceof AuthError) signOutLocally();
      setSearchFailed(true);
      setSearchStatus((error as Error).message);
    } finally {
      setSearching(false);
    }
  }

  function reopenSearch(item: SearchHistory) {
    setUploadedImage(item.thumb);
    setMatches([]);
    setSearchFailed(false);
    setSearchStatus("검색 기록을 불러오는 중…");
    setPage("results");
    backend.fetchHistoryResults(item.id).then((results) => {
      setMatches(results);
      setSearchStatus(`${formatDate(item.searched_at)} 검색 · ${results.length}개 결과`);
    }, (error) => { setSearchFailed(true); setSearchStatus((error as Error).message); if (error instanceof AuthError) signOutLocally(); });
  }

  async function openCamera() {
    try {
      setStream(await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1920 }, height: { ideal: 1080 } } }));
    } catch (error) {
      const name = (error as Error).name;
      window.alert(name === "NotAllowedError" ? "브라우저에서 카메라 권한을 허용해 주세요."
        : name === "NotFoundError" ? "연결된 카메라가 없어요."
        : "카메라를 열 수 없어요. (HTTPS 또는 localhost에서만 동작해요)");
    }
  }

  function capture() {
    const video = videoRef.current!;
    const canvas = document.createElement("canvas");
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d")!.drawImage(video, 0, 0);
    canvas.toBlob((blob) => { if (blob) loadImage(new File([blob], "camera.jpg", { type: "image/jpeg" }), "카메라 촬영"); }, "image/jpeg", 0.92);
  }

  function dropImage(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    loadImage(event.dataTransfer.files?.[0]);
  }

  function toggleFavorite(item: Product) {
    if (!loggedIn) return window.alert("찜 기능은 로그인 후 이용할 수 있어요.");
    const key = productKey(item);
    const previous = favorites;
    const saved = !previous.some((favorite) => productKey(favorite) === key);
    setFavorites(saved ? [item, ...previous] : previous.filter((favorite) => productKey(favorite) !== key));
    backend.saveFavorite(item, saved).catch((error) => { setFavorites(previous); fail(error); });
  }

  function removeHistory(id: number) {
    setHistory((current) => current.filter((item) => item.id !== id));
    backend.removeHistory(id).catch((error) => { fail(error); refreshHistory(); });
  }

  function clearHistory() {
    setHistory([]);
    setCanRestore(true);
    backend.clearHistory().catch((error) => { fail(error); refreshHistory(); });
  }

  function restoreHistory() {
    backend.restoreHistory().then(() => { setCanRestore(false); refreshHistory(); }, fail);
  }

  async function signOut() {
    await backend.logout().catch(() => {});
    signOutLocally();
    setPage("home");
  }

  function openUploadMode() {
    setIsClosingUpload(false);
    setUploadMode(true);
  }

  function closeUploadMode() {
    if (isClosingUpload) return;
    setStream(undefined);
    setIsClosingUpload(true);
    window.setTimeout(() => {
      setUploadMode(false);
      setIsClosingUpload(false);
    }, 650);
  }

  return <main className="lookfind">
    <header className={uploadMode ? "site-header upload-active" : "site-header"}>
      <button className="wordmark" onClick={() => setPage("home")}>LOOK<span>•</span>FIND</button>
      <nav aria-label="주 메뉴">
        {([ ["home", "SEARCH"], ["history", "ARCHIVE"], ["favorites", "SAVED"], ["results", "RESULTS"] ] as const).map(([id, label]) =>
          <button className={page === id ? "active" : ""} key={id} onClick={() => setPage(id)}>{label}</button>)}
      </nav>
      <button className="account" title={user ?? undefined} onClick={() => { if (loggedIn) signOut(); else setPage("login"); }}>{loggedIn ? "LOGOUT" : "LOGIN"}</button>
    </header>

    {page === "home" ? <section className="home">
      <section className="hero">
        <input ref={fileInput} className="file-input" type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseImage} />
        <div className="hero-copy">
          <h1>LOOKFIND</h1>
          <p>사진 한 장으로 원하는 스타일을 찾아보세요.<br />사진 속 옷을 AI가 하나씩 분석하고,<br />비슷한 디자인의 상품을 찾아드립니다.<br />무신사, 지그재그, 에이블리의 상품을 한눈에 비교하고<br />당신이 찾던 옷을 가장 쉽게 발견해보세요.</p>
          <button onClick={openUploadMode}>PHOTO UPLOAD <span>↗</span></button>
        </div>
        <div className="hero-image"><Image src="/lookfind-hero.png" alt="LookFind 스타일 이미지" fill priority sizes="(max-width: 700px) 100vw, 50vw" /><div className={`analysis-layer stage-${analysisStage}`} aria-label="AI 의류 분석 표시"><div className="analysis-box shirt"><span>TOP</span><div className="analysis-crop crop-shirt"><small>TOP</small></div></div><div className="analysis-box pants"><span>PANTS</span><div className="analysis-crop crop-pants"><small>PANTS</small></div></div><div className="analysis-box boots"><span>BOOTS</span><div className="analysis-crop crop-boots"><small>BOOTS</small></div></div></div></div>
      </section>
    </section> : page === "history" ? <History loggedIn={loggedIn} history={history} remove={removeHistory} clear={clearHistory} restore={restoreHistory} canRestore={canRestore} reopen={reopenSearch} /> : page === "favorites" ? <Favorites loggedIn={loggedIn} items={favorites} onFavorite={toggleFavorite} /> : page === "login" ? <Login key={resetToken ?? "login"} resetToken={resetToken} onLogin={(email) => { setUser(email); setResetToken(null); setPage("home"); }} /> : <SearchTestPage image={uploadedImage} matches={matches} status={searchStatus} searching={searching} failed={searchFailed} filter={sourceFilter} setFilter={setSourceFilter} savedKeys={favorites.map(productKey)} onFavorite={toggleFavorite} />}
    {uploadMode && <section className={isClosingUpload ? "upload-mode closing" : "upload-mode"} aria-modal="true" role="dialog"><button className="close-upload" onClick={closeUploadMode} aria-label="업로드 화면 닫기">×</button><div className="upload-content"><h2>UPLOAD PHOTO</h2><div className={isDragging ? "upload-finder dragging" : "upload-finder"} onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={dropImage}><span className="finder-corner top-left" /><span className="finder-corner top-right" /><span className="finder-corner bottom-left" /><span className="finder-corner bottom-right" />{stream ? <><video ref={videoRef} autoPlay playsInline muted aria-label="카메라 미리보기" /><span className="recording">● REC</span><div className="camera-actions"><button className="upload-mode-button" onClick={capture}>찰칵 <span>●</span></button><button className="upload-mode-button" onClick={() => setStream(undefined)}>취소</button></div></> : <><span className="recording">● REC</span><p>사진을 이곳에 끌어다 놓거나 파일을 업로드 해주세요.</p><div className="finder-buttons"><button className="upload-mode-button" onClick={() => fileInput.current?.click()}>SELECT FILE <span>↗</span></button><button className="upload-mode-button" onClick={openCamera}>CAMERA <span>●</span></button></div><small>JPG, PNG, WEBP · MAX 10MB</small></>}</div></div></section>}
  </main>;
}

function SearchTestPage({ image, matches, status, searching, failed, filter, setFilter, savedKeys, onFavorite }: { image: string | null; matches: Product[]; status: string; searching: boolean; failed: boolean; filter: string; setFilter: (filter: string) => void; savedKeys: string[]; onFavorite: (item: Product) => void }) {
  const filters = [{ id: "all", label: "ALL" }, { id: "musinsa", label: "MUSINSA" }, { id: "zigzag", label: "ZIGZAG" }, { id: "ably", label: "ABLY" }];
  const [displayedFilter, setDisplayedFilter] = useState(filter);
  const [pendingFilter, setPendingFilter] = useState<string | null>(null);
  const [isSourceSwap, setIsSourceSwap] = useState(false);
  const [swapPreviousCount, setSwapPreviousCount] = useState(0);
  const [departingCards, setDepartingCards] = useState<Product[]>([]);
  const [isProductsHeadingVisible, setIsProductsHeadingVisible] = useState(true);
    const cardRefs = useRef(new Map<string, HTMLElement>());
  const previousCardPositions = useRef(new Map<string, DOMRect>());
  const filterTimer = useRef<number | null>(null);
  const scrollResetFrame = useRef<number | null>(null);
  const matchGridRef = useRef<HTMLDivElement>(null);
  const visibleMatches = matches.filter((item) => displayedFilter === "all" || item.platform === displayedFilter);
  const displayMatches = isSourceSwap && !pendingFilter ? [...visibleMatches, ...departingCards] : visibleMatches;
  const activeIndex = filters.findIndex(({ id }) => id === filter);

  useEffect(() => () => {
    if (filterTimer.current) window.clearTimeout(filterTimer.current);
    if (scrollResetFrame.current) window.cancelAnimationFrame(scrollResetFrame.current);
  }, []);

  useLayoutEffect(() => {
    if (!previousCardPositions.current.size) return;
    cardRefs.current.forEach((card, id) => {
      const previous = previousCardPositions.current.get(id);
      if (!previous) return;
      const next = card.getBoundingClientRect();
      const x = previous.left - next.left;
      const y = previous.top - next.top;
      if (x || y) card.animate([{ transform: `translate(${x}px, ${y}px)` }, { transform: "translate(0, 0)" }], { duration: 420, easing: "cubic-bezier(.2, .8, .25, 1)" });
    });
    previousCardPositions.current.clear();
  }, [displayedFilter]);

  const changeFilter = (nextFilter: string) => {
    if (nextFilter === filter || pendingFilter || isSourceSwap) return;
    const sourceSwap = displayedFilter !== "all" && nextFilter !== "all";
    const nextMatches = matches.filter((item) => nextFilter === "all" || item.platform === nextFilter);
    const swapDelay = sourceSwap ? 170 : 180;
    cardRefs.current.forEach((card, id) => previousCardPositions.current.set(id, card.getBoundingClientRect()));
    if (sourceSwap) {
      setSwapPreviousCount(visibleMatches.length);
      setDepartingCards(nextMatches.length < visibleMatches.length ? visibleMatches.slice(nextMatches.length) : []);
    } else setDepartingCards([]);
    const grid = matchGridRef.current;
    if (grid && grid.scrollTop > 0) {
      if (scrollResetFrame.current) window.cancelAnimationFrame(scrollResetFrame.current);
      const startingScrollTop = grid.scrollTop;
      let startedAt: number | null = null;
      const duration = 260;
      const scrollStep = (now: number) => {
        if (startedAt === null) startedAt = now;
        const progress = Math.min((now - startedAt) / duration, 1);
        const eased = 1 - (1 - progress) ** 3;
        grid.scrollTop = startingScrollTop * (1 - eased);
        if (progress < 1) scrollResetFrame.current = window.requestAnimationFrame(scrollStep);
      };
      scrollResetFrame.current = window.requestAnimationFrame(scrollStep);
    }
    setIsSourceSwap(sourceSwap);
    setPendingFilter(nextFilter);
    setFilter(nextFilter);
    filterTimer.current = window.setTimeout(() => {
      setDisplayedFilter(nextFilter);
      setPendingFilter(null);
      if (sourceSwap) window.setTimeout(() => { setIsSourceSwap(false); setDepartingCards([]); }, 560);
    }, swapDelay);
  };

  return <section className="test-search">
    <div className="test-heading"><div><h1>SIMILAR LOOKS</h1></div></div>
    <div className="test-controls">
      <p className="test-control-label">YOUR PHOTO</p>
      <div className="matches-controls">
        <p className={`test-control-label matched-products-label ${isProductsHeadingVisible ? "" : "is-hidden"}`}>MATCHED PRODUCTS</p>
        <nav className="source-filter" aria-label="플랫폼 필터">
          <span className={`filter-indicator at-${activeIndex}`} aria-hidden="true" />
          {filters.map(({ id, label }) => <button className={filter === id ? "active" : ""} key={id} onClick={() => changeFilter(id)}>{label}</button>)}
        </nav>
      </div>
    </div>
    <div className="test-layout">
      <aside className="uploaded-column"><div className="uploaded-photo" style={{ backgroundImage: `url(${image ?? "/lookfind-hero.png"})` }} /><small className={failed ? "search-error" : ""} aria-live="polite">{status || "사진을 올리면 상의 영역을 분석해 비슷한 상품을 찾아드려요."}</small></aside>
      <section className="matches-column"><div className="match-grid" ref={matchGridRef} onScroll={(event) => setIsProductsHeadingVisible(event.currentTarget.scrollTop < 2)}>{!displayMatches.length && !failed && <p className="collection-empty" style={{ gridColumn: "1 / -1" }}>{searching ? "검색 중…" : matches.length ? "이 플랫폼의 상품은 아직 없어요." : "사진을 업로드하면 비슷한 상품이 여기에 표시돼요."}</p>}{displayMatches.map((item, index) => {
        const isLeaving = !isSourceSwap && Boolean(pendingFilter && pendingFilter !== "all" && item.platform !== pendingFilter);
        const pendingMatchCount = pendingFilter ? matches.filter((match) => match.platform === pendingFilter).length : visibleMatches.length;
        const departingStart = pendingFilter ? pendingMatchCount : visibleMatches.length;
        const isDepartingCard = isSourceSwap && index >= departingStart;
        const isAdditionalCard = isSourceSwap && !pendingFilter && index >= swapPreviousCount;
        const id = productKey(item);
        const cardKey = isSourceSwap ? `swap-slot-${index}` : id;
        const animationDelay = isAdditionalCard ? `${(index - swapPreviousCount) * 65}ms` : undefined;
        const isSavedMatch = savedKeys.includes(id);
        return <article className={`match-card ${isLeaving ? "leaving" : ""} ${isSourceSwap && !isAdditionalCard && !isDepartingCard ? "source-flipping" : ""} ${isAdditionalCard ? "source-floating" : ""} ${isDepartingCard ? "source-departing" : ""}`} key={cardKey} style={{ animationDelay }} ref={(element) => { if (element) cardRefs.current.set(id, element); else cardRefs.current.delete(id); }}><a className="match-link" href={item.product_url} target="_blank" rel="noopener noreferrer"><div className="match-photo has-photo" style={photoStyle(productImage(item))}><span>{sourceLabels[item.platform] ?? item.platform} · {Math.round(item.similarity * 100)}%</span></div><h3 title={item.goods_name}>{item.goods_name}</h3></a><div className="match-product-line"><small>{item.brand_name}</small><button className={isSavedMatch ? "match-favorite saved" : "match-favorite"} onClick={() => onFavorite(item)} aria-label={`${item.goods_name} ${isSavedMatch ? "저장 취소" : "저장"}`}><HeartIcon filled={isSavedMatch} /></button></div><strong>{won(item.price)}</strong></article>;
      })}</div></section>
    </div>
  </section>;
}

function History({ loggedIn, history, remove, clear, restore, canRestore, reopen }: { loggedIn: boolean; history: SearchHistory[]; remove: (id: number) => void; clear: () => void; restore: () => void; canRestore: boolean; reopen: (item: SearchHistory) => void }) {
  const [isClearing, setIsClearing] = useState(false);
  const [removingId, setRemovingId] = useState<number | null>(null);
  const cardRefs = useRef(new Map<number, HTMLElement>());
  const previousCardPositions = useRef(new Map<number, DOMRect>());

  useLayoutEffect(() => {
    if (!previousCardPositions.current.size) return;
    cardRefs.current.forEach((card, id) => {
      const previous = previousCardPositions.current.get(id);
      if (!previous) return;
      const next = card.getBoundingClientRect();
      const x = previous.left - next.left;
      const y = previous.top - next.top;
      if (x || y) card.animate([{ transform: `translate(${x}px, ${y}px)` }, { transform: "translate(0, 0)" }], { duration: 360, easing: "cubic-bezier(.2, .8, .25, 1)" });
    });
    previousCardPositions.current.clear();
  }, [history]);

  const clearWithAnimation = () => {
    if (!history.length || isClearing || removingId) return;
    setIsClearing(true);
    window.setTimeout(() => {
      clear();
      setIsClearing(false);
    }, 700);
  };
  const removeWithAnimation = (id: number) => {
    if (isClearing || removingId) return;
    setRemovingId(id);
    window.setTimeout(() => {
      cardRefs.current.forEach((card, cardId) => {
        if (cardId !== id) previousCardPositions.current.set(cardId, card.getBoundingClientRect());
      });
      remove(id);
      setRemovingId(null);
    }, 300);
  };
  if (!loggedIn) return <MemberGate title="검색 기록은 로그인 후 저장돼요" text="로그인하면 이전에 검색한 사진과 결과를 다시 확인할 수 있어요." />;
  return <section className="collection-page">
    <div className="collection-heading"><h1>ARCHIVE</h1><div className="collection-actions"><button className="collection-action" onClick={clearWithAnimation} disabled={!history.length || isClearing || Boolean(removingId)}>CLEAR ALL <span>↗</span></button><button className="collection-return" onClick={restore} disabled={!canRestore || isClearing || Boolean(removingId)}>RETURN <span>↶</span></button></div></div>
    {history.length ? <div className={isClearing ? "archive-grid is-clearing" : "archive-grid"}>{history.map((item, index) => <article className={`archive-card archive-tone-${index % 3} ${removingId === item.id ? "is-removing" : ""}`} key={item.id} style={isClearing ? { animationDelay: `${index * 42}ms` } : undefined} ref={(element) => { if (element) cardRefs.current.set(item.id, element); else cardRefs.current.delete(item.id); }}>
      <button className="archive-open" onClick={() => reopen(item)}><div className={item.thumb ? "archive-visual saved-visual has-photo" : "archive-visual saved-visual"} style={item.thumb ? photoStyle(item.thumb) : undefined} /><div className="archive-info"><h2>{item.label}</h2><p>{formatDate(item.searched_at)}</p><strong>{item.count} MATCHES</strong></div></button>
      <button className="archive-remove" aria-label={`${item.label} 삭제`} onClick={() => removeWithAnimation(item.id)} disabled={isClearing || Boolean(removingId)}>×</button>
    </article>)}</div> : <p className="collection-empty">아직 검색 기록이 없어요. 사진을 올려 첫 검색을 해보세요.</p>}
  </section>;
}

function Favorites({ loggedIn, items, onFavorite }: { loggedIn: boolean; items: Product[]; onFavorite: (item: Product) => void }) {
  if (!loggedIn) return <MemberGate title="찜 목록은 로그인 후 이용할 수 있어요" text="마음에 드는 상품을 저장하고 나중에 비교해보세요." />;
  return <section className="collection-page">
    <div className="collection-heading"><h1>SAVED LOOKS</h1><span className="collection-count">{items.length} ITEMS</span></div>
    {items.length ? <div className="saved-grid">{items.map((item) => <article className="saved-card" key={productKey(item)}>
      <a className="match-link" href={item.product_url} target="_blank" rel="noopener noreferrer"><div className="saved-visual has-photo" style={photoStyle(productImage(item))}><span>{sourceLabels[item.platform] ?? item.platform}</span></div><h2 title={item.goods_name}>{item.goods_name}</h2></a><div className="saved-product-line"><p>{item.brand_name}</p><button className="saved-favorite" aria-label={`${item.goods_name} 저장 취소`} onClick={() => onFavorite(item)}><HeartIcon filled /></button></div><strong>{won(item.price)}</strong>
    </article>)}</div> : <p className="collection-empty">아직 저장한 제품이 없습니다.</p>}
  </section>;
}

type LoginMode = "login" | "signup" | "forgot" | "reset";
const loginCopy: Record<LoginMode, { eyebrow: string; title: [string, string]; submit: string }> = {
  login: { eyebrow: "MEMBER LOGIN", title: ["WELCOME", "BACK"], submit: "LOGIN" },
  signup: { eyebrow: "CREATE ACCOUNT", title: ["JOIN", "LOOKFIND"], submit: "SIGN UP" },
  forgot: { eyebrow: "FORGOT PASSWORD", title: ["RESET", "PASSWORD"], submit: "SEND LINK" },
  reset: { eyebrow: "NEW PASSWORD", title: ["SET NEW", "PASSWORD"], submit: "SAVE & LOGIN" },
};

function Login({ onLogin, resetToken }: { onLogin: (email: string) => void; resetToken: string | null }) {
  const [mode, setMode] = useState<LoginMode>(resetToken ? "reset" : "login");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const copy = loginCopy[mode];
  const switchTo = (next: LoginMode) => { setMode(next); setError(""); setNotice(""); };
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const email = String(form.get("email") ?? "");
    const password = String(form.get("password") ?? "");
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (mode === "forgot") {
        await backend.requestPasswordReset(email);
        setNotice("가입된 이메일이면 재설정 링크를 보냈어요. 30분 안에 링크를 열어 주세요.");
        return;
      }
      const session = mode === "reset" ? await backend.resetPassword(resetToken ?? "", password) : await backend.authenticate(mode, email, password);
      writeToken(session.token);
      onLogin(session.email);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return <section className="login-page"><div className="login-intro"><p>WELCOME TO</p><h1>LOOKFIND</h1><span>사진으로 찾고, 취향으로 저장하세요.</span></div><form className="login-panel" onSubmit={submit}><p>{copy.eyebrow}</p><h2>{copy.title[0]}<br />{copy.title[1]}</h2>
    {mode !== "reset" && <label>EMAIL<input type="email" name="email" autoComplete="email" placeholder="you@example.com" required /></label>}
    {mode !== "forgot" && <label>{mode === "reset" ? "NEW PASSWORD" : "PASSWORD"}<input type="password" name="password" autoComplete={mode === "login" ? "current-password" : "new-password"} minLength={mode === "login" ? undefined : 8} placeholder={mode === "login" ? "••••••••" : "8자 이상"} required /></label>}
    {error && <small className="search-error" role="alert">{error}</small>}
    {notice && <small role="status">{notice}</small>}
    <button type="submit" disabled={busy}>{copy.submit} <span>↗</span></button>
    {mode === "login" && <small><button type="button" className="login-switch" onClick={() => switchTo("forgot")}>비밀번호를 잊으셨나요?</button></small>}
    <small>{mode === "signup" ? "이미 계정이 있으신가요? " : mode === "login" ? "아직 계정이 없으신가요? " : ""}<button type="button" className="login-switch" onClick={() => switchTo(mode === "login" ? "signup" : "login")}>{mode === "login" ? "SIGN UP" : "LOGIN"}</button></small>
  </form></section>;
}

function MemberGate({ title, text }: { title: string; text: string }) { return <section className="member-gate"><b>✦</b><h1>{title}</h1><p>{text}</p></section>; }

function HeartIcon({ filled = false }: { filled?: boolean }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 20.8-1.32-1.2C5.48 14.9 2.4 12.1 2.4 8.58c0-2.88 2.26-5.18 5.13-5.18 1.62 0 3.18.75 4.2 1.96a5.53 5.53 0 0 1 4.2-1.96c2.87 0 5.13 2.3 5.13 5.18 0 3.52-3.08 6.32-8.28 11.02L12 20.8Z" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={filled ? "1" : "1.15"} strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
