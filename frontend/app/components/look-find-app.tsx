"use client";

import { ChangeEvent, DragEvent, useEffect, useLayoutEffect, useRef, useState } from "react";
import Image from "next/image";
import { ApiError, errorMessage, getFavorites, getMe, photoStyle, productImage, productKey, saveFavorite, searchImage, signOut, won } from "../apis/backend";
import AuthForm from "./auth-form";
import LoginCurtain from "./login-curtain";
import MemberGate from "./member-gate";
import HistoryView from "./history-view";
import MyPage from "./my-page";
import { sourceLabels } from "../constants/look-find";
import type { Product, User } from "../types/api";

type Page = "mypage" | "home" | "history" | "favorites" | "results";

const LOADING_MESSAGE = "상의 영역을 찾고 비슷한 상품을 검색하고 있어요. 첫 검색은 모델 로딩 때문에 오래 걸릴 수 있어요.";

export default function LookFindApp() {
  const [page, setPage] = useState<Page>("home");
  const [loginOpen, setLoginOpen] = useState(false);
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const loggedIn = Boolean(user);
  const [favorites, setFavorites] = useState<Product[]>([]);
  const [uploadMode, setUploadMode] = useState(false);
  const [isClosingUpload, setIsClosingUpload] = useState(false);
  const uploadCloseTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [uploadedImage, setUploadedImage] = useState<string | null>(null);
  const [sourceFilter, setSourceFilter] = useState("all");
  const [analysisStage, setAnalysisStage] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [matches, setMatches] = useState<Product[]>([]);
  const [searchStatus, setSearchStatus] = useState("");
  const [searching, setSearching] = useState(false);
  const [searchFailed, setSearchFailed] = useState(false);
  const searchController = useRef<AbortController | null>(null);
  const [stream, setStream] = useState<MediaStream>();
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const stageLock = useRef(false);
  const touchStart = useRef(0);

  // ?login_error=kakao comes back from a failed Kakao login; ?reset=<token> from a password reset mail.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("login_error") === "kakao") setNotice("카카오 로그인을 완료하지 못했어요. 잠시 후 다시 시도해 주세요."); // eslint-disable-line react-hooks/set-state-in-effect
    const token = params.get("reset");
    if (token) { setResetToken(token); setLoginOpen(true); }
    if (params.size) window.history.replaceState(null, "", window.location.pathname);
  }, []);
  // Restore the server session (HttpOnly cookie) on load.
  useEffect(() => {
    const controller = new AbortController();
    getMe(controller.signal).then(setUser).catch(error => {
      if (!controller.signal.aborted && !(error instanceof ApiError && error.status === 401)) setNotice(errorMessage(error));
    }).finally(() => { if (!controller.signal.aborted) setAuthLoading(false); });
    return () => controller.abort();
  }, []);
  useEffect(() => {
    if (!user) return;
    getFavorites().then(setFavorites, fail);
  }, [user]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => {
    searchController.current?.abort();
    if (uploadCloseTimer.current) clearTimeout(uploadCloseTimer.current);
  }, []);

  useEffect(() => {
    if (page !== "home" || uploadMode || loginOpen) return;

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
  }, [page, uploadMode, loginOpen]);

  // Attach the live camera to <video>; stopping tracks here also covers cancel/capture/close.
  useEffect(() => {
    if (!stream) return;
    videoRef.current!.srcObject = stream;
    return () => stream.getTracks().forEach((track) => track.stop());
  }, [stream]);

  function signOutLocally() {
    searchController.current?.abort();
    setUser(null);
    setFavorites([]);
  }

  function fail(error: unknown) {
    if (error instanceof ApiError && error.status === 401) { signOutLocally(); setNotice("로그인이 만료됐어요. 다시 로그인해 주세요."); return; }
    setNotice(errorMessage(error));
  }

  function openLogin() {
    window.scrollTo({ top: 0, behavior: "instant" });
    if (uploadCloseTimer.current) clearTimeout(uploadCloseTimer.current);
    setStream(undefined);
    setIsClosingUpload(false);
    setLoginOpen(true);
  }

  function navigate(next: Page) {
    if (uploadCloseTimer.current) clearTimeout(uploadCloseTimer.current);
    setStream(undefined);
    setUploadMode(false);
    setIsClosingUpload(false);
    setLoginOpen(false);
    setPage(next);
  }

  function chooseImage(event: ChangeEvent<HTMLInputElement>) {
    loadImage(event.target.files?.[0]);
    event.target.value = "";
  }

  async function loadImage(file?: File, label = file?.name ?? "업로드 사진") {
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 10 * 1024 * 1024) { setNotice("10MB 이하의 이미지 파일을 선택해 주세요."); return; }
    if (authLoading) { setNotice("로그인 상태를 확인 중입니다. 잠시 후 다시 시도해 주세요."); return; }
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    if (uploadedImage?.startsWith("blob:")) URL.revokeObjectURL(uploadedImage);
    setNotice("");
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
      const data = await searchImage(file, label, controller.signal);
      if (controller.signal.aborted) return;
      setMatches(data.results);
      setSearchStatus([
        data.used_top_mask ? `상의 비율 ${(data.top_ratio * 100).toFixed(1)}%` : "상의를 찾지 못해 사진 전체로 검색했어요",
        `${(data.elapsed_ms / 1000).toFixed(1)}초`,
        `${data.results.length}개 결과`,
        loggedIn ? "ARCHIVE에 저장됨" : "로그인하면 검색 기록이 저장돼요",
      ].join(" · "));
    } catch (error) {
      if (controller.signal.aborted) return;
      if (error instanceof ApiError && error.status === 401) signOutLocally();
      setSearchFailed(true);
      setSearchStatus(errorMessage(error));
    } finally {
      if (!controller.signal.aborted) setSearching(false);
    }
  }

  async function openCamera() {
    try {
      setStream(await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1920 }, height: { ideal: 1080 } } }));
    } catch (error) {
      const name = (error as Error).name;
      setNotice(name === "NotAllowedError" ? "브라우저에서 카메라 권한을 허용해 주세요."
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
    if (!loggedIn) return openLogin();
    const key = productKey(item);
    const previous = favorites;
    const saved = !previous.some((favorite) => productKey(favorite) === key);
    setFavorites(saved ? [item, ...previous] : previous.filter((favorite) => productKey(favorite) !== key));
    saveFavorite(item, saved).catch((error) => { setFavorites(previous); fail(error); });
  }

  async function logout() {
    setAuthLoading(true);
    try {
      await signOut();
      signOutLocally();
      setMatches([]); setUploadedImage(null); setSearching(false); setSearchStatus("");
      setPage("home"); setNotice("");
    } catch (error) { setNotice(errorMessage(error)); }
    finally { setAuthLoading(false); }
  }

  function onLogin(nextUser: User) {
    searchController.current?.abort();
    setSearching(false); setMatches([]); setUploadedImage(null); setSearchStatus("");
    setUser(nextUser); setResetToken(null); setNotice(""); setLoginOpen(false); setPage("home");
  }

  function openUploadMode() {
    setIsClosingUpload(false);
    setUploadMode(true);
  }

  function closeUploadMode() {
    if (isClosingUpload) return;
    setStream(undefined);
    setIsClosingUpload(true);
    uploadCloseTimer.current = setTimeout(() => {
      setUploadMode(false);
      setIsClosingUpload(false);
    }, 650);
  }

  return <main className="lookfind">
    <header className={loginOpen ? "site-header login-active" : uploadMode ? "site-header upload-active" : "site-header"}>
      <button className="wordmark" onClick={() => navigate("home")}>LOOK<span>•</span>FIND</button>
      <nav aria-label="주 메뉴">
        {([ ["home", "SEARCH"], ["history", "ARCHIVE"], ["favorites", "SAVED"], ["results", "RESULTS"] ] as const).map(([id, label]) =>
          <button className={!loginOpen && page === id ? "active" : ""} key={id} onClick={() => navigate(id)}>{label}</button>)}
        {user && <button className={!loginOpen && page === "mypage" ? "active" : ""} aria-current={!loginOpen && page === "mypage" ? "page" : undefined} onClick={() => navigate("mypage")}>MY PAGE</button>}
      </nav>
      {user ? <div className="account-menu">
        <button className="account account-profile" title={user.email} aria-haspopup="menu">
          {user.avatar_url ? <img src={user.avatar_url} alt="" referrerPolicy="no-referrer" /> : <span className="account-avatar-fallback">{(user.display_name || user.email).slice(0, 1).toUpperCase()}</span>}
          <span>{user.display_name || user.email.split("@")[0]}</span><i>⌄</i>
        </button>
        <div className="account-popover" role="menu">
          <span>{user.email}</span>
          <button role="menuitem" onClick={() => void logout()}>LOGOUT</button>
        </div>
      </div> : <button className="account" disabled={authLoading} onClick={openLogin}>{authLoading ? "LOADING…" : "LOGIN"}</button>}
    </header>

    <div inert={loginOpen}>
    {notice && <div className="connection-notice" role="alert">{notice}<button onClick={() => setNotice("")} aria-label="알림 닫기">×</button></div>}
    {page === "home" ? <section className="home">
      <section className="hero">
        <input ref={fileInput} className="file-input" type="file" accept="image/jpeg,image/png,image/webp" onChange={chooseImage} />
        <div className="hero-copy">
          <h1>LOOKFIND</h1>
          <p>사진 한 장으로 원하는 스타일을 찾아보세요.<br />사진 속 옷을 AI가 하나씩 분석하고,<br />비슷한 디자인의 상품을 찾아드립니다.<br />무신사, 지그재그, 에이블리의 상품을 한눈에 비교하고<br />당신이 찾던 옷을 가장 쉽게 발견해보세요.</p>
          <button className="photo-action" onClick={openUploadMode}>PHOTO UPLOAD <span>↗</span></button>
        </div>
        <div className="hero-image"><Image src="/lookfind-hero.png" alt="LookFind 스타일 이미지" fill priority sizes="(max-width: 700px) 100vw, 50vw" /><div className={`analysis-layer stage-${analysisStage}`} aria-label="AI 의류 분석 표시"><div className="analysis-box shirt"><span>TOP</span><div className="analysis-crop crop-shirt"><small>TOP</small></div></div><div className="analysis-box pants"><span>PANTS</span><div className="analysis-crop crop-pants"><small>PANTS</small></div></div><div className="analysis-box boots"><span>BOOTS</span><div className="analysis-crop crop-boots"><small>BOOTS</small></div></div></div></div>
      </section>
    </section> : page === "mypage" ? (user ? <MyPage user={user} busy={authLoading} onHistory={() => navigate("history")} onSaved={() => navigate("favorites")} onLogout={() => void logout()} /> : <MemberGate title="로그인이 필요해요." text="로그인 후 내 계정을 확인할 수 있어요." onLogin={openLogin} />)
      : page === "history" ? (authLoading ? <p className="api-status">로그인 상태를 확인하고 있습니다…</p> : user ? <HistoryView key={user.id} onLogin={openLogin} onOpen={(item) => {
        searchController.current?.abort();
        setSearching(false); setSearchFailed(false);
        setUploadedImage(item.image_url); setMatches(item.results);
        setSearchStatus(`${new Date(item.searched_at).toLocaleString("ko-KR")} 검색 · ${item.results.length}개 결과`);
        setPage("results");
      }} /> : <MemberGate title="검색 기록은 로그인 후 저장돼요." text="이전에 검색한 사진과 결과를 다시 확인할 수 있어요." onLogin={openLogin} />)
      : page === "favorites" ? <Favorites loggedIn={loggedIn} items={favorites} onFavorite={toggleFavorite} onLogin={openLogin} />
      : <SearchTestPage image={uploadedImage} matches={matches} status={searchStatus} searching={searching} failed={searchFailed} filter={sourceFilter} setFilter={setSourceFilter} savedKeys={favorites.map(productKey)} onFavorite={toggleFavorite} />}
    </div>
    {loginOpen && <LoginCurtain onClose={() => setLoginOpen(false)}><AuthForm key={resetToken ?? "login"} resetToken={resetToken} onLogin={onLogin} /></LoginCurtain>}

    {uploadMode && <section className={isClosingUpload ? "upload-mode closing" : "upload-mode"} inert={loginOpen} aria-hidden={loginOpen || undefined} aria-modal={!loginOpen} role="dialog"><button className="close-upload" onClick={closeUploadMode} aria-label="업로드 화면 닫기">×</button><div className="upload-content"><h2>UPLOAD PHOTO</h2><div className={isDragging ? "upload-finder dragging" : "upload-finder"} onDragOver={(event) => { event.preventDefault(); setIsDragging(true); }} onDragLeave={() => setIsDragging(false)} onDrop={dropImage}><span className="finder-corner top-left" /><span className="finder-corner top-right" /><span className="finder-corner bottom-left" /><span className="finder-corner bottom-right" />{stream ? <><video ref={videoRef} autoPlay playsInline muted aria-label="카메라 미리보기" /><span className="recording">● REC</span><div className="camera-actions"><button className="upload-mode-button" onClick={capture}>찰칵 <span>●</span></button><button className="upload-mode-button" onClick={() => setStream(undefined)}>취소</button></div></> : <><span className="recording">● REC</span><p>사진을 이곳에 끌어다 놓거나 파일을 업로드 해주세요.</p><div className="finder-buttons"><button className="upload-mode-button" onClick={() => fileInput.current?.click()}>SELECT FILE <span>↗</span></button><button className="upload-mode-button" onClick={openCamera}>CAMERA <span>●</span></button></div><small>JPG, PNG, WEBP · MAX 10MB</small></>}</div></div></section>}
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

function Favorites({ loggedIn, items, onFavorite, onLogin }: { loggedIn: boolean; items: Product[]; onFavorite: (item: Product) => void; onLogin: () => void }) {
  if (!loggedIn) return <MemberGate title="찜 목록은 로그인 후 이용할 수 있어요" text="마음에 드는 상품을 저장하고 나중에 비교해보세요." onLogin={onLogin} />;
  return <section className="collection-page">
    <div className="collection-heading"><h1>SAVED LOOKS</h1><span className="collection-count">{items.length} ITEMS</span></div>
    {items.length ? <div className="saved-grid">{items.map((item) => <article className="saved-card" key={productKey(item)}>
      <a className="match-link" href={item.product_url} target="_blank" rel="noopener noreferrer"><div className="saved-visual has-photo" style={photoStyle(productImage(item))}><span>{sourceLabels[item.platform] ?? item.platform}</span></div><h2 title={item.goods_name}>{item.goods_name}</h2></a><div className="saved-product-line"><p>{item.brand_name}</p><button className="saved-favorite" aria-label={`${item.goods_name} 저장 취소`} onClick={() => onFavorite(item)}><HeartIcon filled /></button></div><strong>{won(item.price)}</strong>
    </article>)}</div> : <p className="collection-empty">아직 저장한 제품이 없습니다.</p>}
  </section>;
}

function HeartIcon({ filled = false }: { filled?: boolean }) {
  return <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m12 20.8-1.32-1.2C5.48 14.9 2.4 12.1 2.4 8.58c0-2.88 2.26-5.18 5.13-5.18 1.62 0 3.18.75 4.2 1.96a5.53 5.53 0 0 1 4.2-1.96c2.87 0 5.13 2.3 5.13 5.18 0 3.52-3.08 6.32-8.28 11.02L12 20.8Z" fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={filled ? "1" : "1.15"} strokeLinecap="round" strokeLinejoin="round" /></svg>;
}
