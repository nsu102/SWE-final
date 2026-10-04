"use client";

import { FormEvent, useState } from "react";
import { requestPasswordReset, resetPassword, signIn, signUp } from "../apis/auth";
import { errorMessage } from "../utils/error";
import type { User } from "../types/api";

type Mode = "login" | "register" | "forgot" | "reset";
const titles: Record<Mode, string> = { login: "LOGIN", register: "SIGN UP", forgot: "RESET PASSWORD", reset: "NEW PASSWORD" };
const submits: Record<Mode, string> = { login: "LOGIN", register: "SIGN UP", forgot: "SEND LINK", reset: "SAVE & LOGIN" };

export default function AuthForm({ onLogin, resetToken }: { onLogin: (user: User) => void; resetToken?: string | null }) {
  const [mode, setMode] = useState<Mode>(resetToken ? "reset" : "login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const newPassword = mode === "register" || mode === "reset";
  const switchTo = (next: Mode) => { setMode(next); setError(""); setNotice(""); };
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const email = String(data.get("email") ?? "");
    const password = String(data.get("password") ?? "");
    if (newPassword && password !== data.get("confirmation")) { setError("비밀번호가 일치하지 않습니다."); return; }
    setBusy(true); setError(""); setNotice("");
    try {
      if (mode === "forgot") {
        await requestPasswordReset(email);
        setNotice("가입된 이메일이면 재설정 링크를 보냈어요. 30분 안에 링크를 열어 주세요.");
      } else {
        onLogin(await (mode === "reset" ? resetPassword(resetToken ?? "", password) : (mode === "register" ? signUp : signIn)(email, password)));
      }
    }
    catch (error) { setError(errorMessage(error)); }
    finally { setBusy(false); }
  }
  return <section className="login-page">
    <div className="login-intro"><p>WELCOME TO</p><h1>LOOKFIND</h1></div>
    <form className="login-panel" onSubmit={submit} aria-busy={busy}>
      <h2>{titles[mode]}</h2>
      {mode !== "reset" && <label>EMAIL<input type="email" name="email" autoComplete="email" maxLength={254} placeholder="you@example.com" required disabled={busy} /></label>}
      {mode !== "forgot" && <label>{mode === "reset" ? "NEW PASSWORD" : "PASSWORD"}<input type="password" name="password" autoComplete={newPassword ? "new-password" : "current-password"} minLength={8} maxLength={128} placeholder="8자 이상 입력" required disabled={busy} /></label>}
      {newPassword && <label>CONFIRM PASSWORD<input type="password" name="confirmation" autoComplete="new-password" minLength={8} maxLength={128} required disabled={busy} /></label>}
      {error && <p className="api-error" role="alert">{error}</p>}
      {notice && <p className="api-status" role="status">{notice}</p>}
      <button type="submit" disabled={busy}>{busy ? "처리 중…" : submits[mode]} <span>↗</span></button>
      {(mode === "login" || mode === "register") && <a className="kakao-login" href="/api/auth/kakao">KAKAO로 계속하기 <span>↗</span></a>}
      {mode === "login" && <small><button className="auth-switch" type="button" disabled={busy} onClick={() => switchTo("forgot")}>비밀번호를 잊으셨나요?</button></small>}
      <small>{mode === "login" ? "아직 계정이 없으신가요?" : mode === "register" ? "이미 계정이 있으신가요?" : ""} <button className="auth-switch" type="button" disabled={busy} onClick={() => switchTo(mode === "login" ? "register" : "login")}>{mode === "login" ? "SIGN UP" : "LOGIN"}</button></small>
    </form>
  </section>;
}
