"use client";

import { createContext, ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getMe, signOut } from "../apis/auth";
import { getFavorites, saveFavorite } from "../apis/favorites";
import { getHistoryDetail } from "../apis/history";
import { searchImage } from "../apis/search";
import { LOADING_MESSAGE, MAX_INPUT_BYTES } from "../constants/look-find";
import { downscaleImage } from "../utils/image";
import type { Product, User } from "../types/api";
import { errorMessage, isUnauthorized } from "../utils/error";
import { dateTime } from "../utils/format";
import { productKey } from "../utils/product";
import AuthForm from "../components/auth-form";
import LoginCurtain from "../components/login-curtain";
import SiteHeader from "../components/site-header";
import UploadOverlay from "../components/upload-overlay";

type Search = { image: string | null; matches: Product[]; status: string; searching: boolean; failed: boolean; historyId: string | null; canRetry: boolean };
const emptySearch: Search = { image: null, matches: [], status: "", searching: false, failed: false, historyId: null, canRetry: false };

type LookFind = {
  user: User | null;
  authLoading: boolean;
  favorites: Product[];
  search: Search;
  openLogin: () => void;
  openUpload: () => void;
  logout: () => Promise<void>;
  runSearch: (file?: File, label?: string) => void;
  retrySearch: () => void;
  openHistory: (id: string) => void;
  toggleFavorite: (item: Product) => void;
  setNotice: (notice: string) => void;
  closeOverlays: () => void;
  overlayOpen: boolean;
};

const LookFindContext = createContext<LookFind | null>(null);

export function useLookFind() {
  const value = useContext(LookFindContext);
  if (!value) throw new Error("useLookFind must be used inside <LookFindProvider>");
  return value;
}

/** App-wide state shared by every route: session, favorites, the current search and the login/upload overlays. */
export default function LookFindProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<User | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [notice, setNotice] = useState("");
  const [favorites, setFavorites] = useState<Product[]>([]);
  const [search, setSearch] = useState<Search>(emptySearch);
  const [loginOpen, setLoginOpen] = useState(false);
  const [resetToken, setResetToken] = useState<string | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const searchController = useRef<AbortController | null>(null);
  const lastUpload = useRef<{ file: File; label: string } | null>(null);

  // ?login_error=kakao comes back from a failed Kakao login; ?reset=<token> from a password reset mail.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get("login_error") === "kakao") setNotice("카카오 로그인을 완료하지 못했어요. 잠시 후 다시 시도해 주세요."); // eslint-disable-line react-hooks/set-state-in-effect
    const token = params.get("reset");
    if (token) { setResetToken(token); setLoginOpen(true); }
    if (params.has("login_error") || token) window.history.replaceState(null, "", window.location.pathname);
  }, []);
  // Restore the server session (HttpOnly cookie) on load.
  useEffect(() => {
    const controller = new AbortController();
    getMe(controller.signal).then(setUser).catch(error => {
      if (!controller.signal.aborted && !isUnauthorized(error)) setNotice(errorMessage(error));
    }).finally(() => { if (!controller.signal.aborted) setAuthLoading(false); });
    return () => controller.abort();
  }, []);
  const signOutLocally = useCallback(() => {
    searchController.current?.abort();
    setUser(null);
    setFavorites([]);
  }, []);
  const fail = useCallback((error: unknown) => {
    if (isUnauthorized(error)) { signOutLocally(); setNotice("로그인이 만료됐어요. 다시 로그인해 주세요."); return; }
    setNotice(errorMessage(error));
  }, [signOutLocally]);
  useEffect(() => {
    if (user) getFavorites().then(setFavorites, fail);
  }, [user, fail]);
  useEffect(() => () => searchController.current?.abort(), []);

  const openLogin = useCallback(() => {
    window.scrollTo({ top: 0, behavior: "instant" });
    setUploadOpen(false);
    setLoginOpen(true);
  }, []);

  const runSearch = useCallback((file?: File, label = file?.name ?? "업로드 사진") => {
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > MAX_INPUT_BYTES) { setNotice("20MB 이하의 이미지 파일을 선택해 주세요."); return; }
    if (authLoading) { setNotice("로그인 상태를 확인 중입니다. 잠시 후 다시 시도해 주세요."); return; }
    lastUpload.current = { file, label };
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    setSearch(current => {
      if (current.image?.startsWith("blob:")) URL.revokeObjectURL(current.image);
      return { ...emptySearch, image: URL.createObjectURL(file), status: LOADING_MESSAGE, searching: true };
    });
    setNotice("");
    setUploadOpen(false);
    router.push("/results");
    // Phone photos are often 5–12MB; the backend only needs ~1024px and Lambda caps request bodies at 6MB.
    downscaleImage(file).then(small => searchImage(small, label, controller.signal)).then(data => {
      if (controller.signal.aborted) return;
      setSearch(current => ({ ...current, searching: false, matches: data.results, status: [
        data.used_top_mask ? `상의 비율 ${(data.top_ratio * 100).toFixed(1)}%` : "상의를 찾지 못해 사진 전체로 검색했어요",
        `${(data.elapsed_ms / 1000).toFixed(1)}초`,
        `${data.results.length}개 결과`,
        user ? "ARCHIVE에 저장됨" : "로그인하면 검색 기록이 저장돼요",
      ].join(" · ") }));
    }, error => {
      if (controller.signal.aborted) return;
      if (isUnauthorized(error)) signOutLocally();
      setSearch(current => ({ ...current, searching: false, failed: true, canRetry: true, status: errorMessage(error) }));
    });
  }, [authLoading, router, signOutLocally, user]);

  const openHistory = useCallback((id: string) => {
    searchController.current?.abort();
    const controller = new AbortController();
    searchController.current = controller;
    setSearch({ ...emptySearch, historyId: id, searching: true, status: "검색 기록을 불러오는 중…" });
    getHistoryDetail(id, controller.signal).then(item => {
      if (controller.signal.aborted) return;
      setSearch({ ...emptySearch, historyId: id, image: item.image_url, matches: item.results,
        status: `${dateTime(item.searched_at)} 검색 · ${item.results.length}개 결과` });
    }, error => {
      if (controller.signal.aborted) return;
      if (isUnauthorized(error)) signOutLocally();
      setSearch({ ...emptySearch, historyId: id, failed: true, status: errorMessage(error) });
    });
  }, [signOutLocally]);

  const toggleFavorite = useCallback((item: Product) => {
    if (!user) return openLogin();
    const key = productKey(item);
    const saved = !favorites.some(favorite => productKey(favorite) === key);
    const previous = favorites;
    setFavorites(saved ? [item, ...previous] : previous.filter(favorite => productKey(favorite) !== key));
    saveFavorite(item, saved).catch(error => { setFavorites(previous); fail(error); });
  }, [fail, favorites, openLogin, user]);

  const logout = useCallback(async () => {
    setAuthLoading(true);
    try {
      await signOut();
      signOutLocally();
      setSearch(emptySearch);
      setNotice("");
      router.push("/");
    } catch (error) { setNotice(errorMessage(error)); }
    finally { setAuthLoading(false); }
  }, [router, signOutLocally]);

  function onLogin(nextUser: User) {
    searchController.current?.abort();
    setSearch(emptySearch);
    setUser(nextUser); setResetToken(null); setNotice(""); setLoginOpen(false);
    router.push("/");
  }

  const retrySearch = useCallback(() => {
    if (lastUpload.current) runSearch(lastUpload.current.file, lastUpload.current.label);
  }, [runSearch]);

  const value: LookFind = {
    user, authLoading, favorites, search, openLogin, logout, runSearch, retrySearch, openHistory, toggleFavorite, setNotice,
    openUpload: () => setUploadOpen(true),
    closeOverlays: () => { setLoginOpen(false); setUploadOpen(false); },
    overlayOpen: loginOpen || uploadOpen,
  };
  return <LookFindContext.Provider value={value}>
    <SiteHeader mode={loginOpen ? "login" : uploadOpen ? "upload" : null} />
    <div className="lookfind-body" inert={loginOpen}>
      {notice && <div className="connection-notice" role="alert">{notice}<button onClick={() => setNotice("")} aria-label="알림 닫기">×</button></div>}
      {children}
    </div>
    {loginOpen && <LoginCurtain onClose={() => setLoginOpen(false)}><AuthForm key={resetToken ?? "login"} resetToken={resetToken} onLogin={onLogin} /></LoginCurtain>}
    {uploadOpen && <UploadOverlay inert={loginOpen} onClose={() => setUploadOpen(false)} onFile={runSearch} onError={setNotice} />}
  </LookFindContext.Provider>;
}
