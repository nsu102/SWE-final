"use client";

import { ChangeEvent, FormEvent, useEffect, useRef, useState } from "react";
import { removeAvatar, updateProfile, uploadAvatar } from "../apis/account";
import { MAX_INPUT_BYTES, PROFILE_NAME_MAX } from "../constants/look-find";
import type { User } from "../types/api";
import { errorMessage } from "../utils/error";
import UserAvatar from "./user-avatar";

type Props = { user: User; onSaved: (user: User) => void; onClose: () => void };

/** MY PAGE → 프로필 수정. Native <dialog>: focus trap, Esc and the backdrop come from the browser. */
export default function ProfileEditModal({ user, onSaved, onClose }: Props) {
  const dialog = useRef<HTMLDialogElement>(null);
  const fileInput = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(user.display_name || user.email.split("@")[0]);
  const [photo, setPhoto] = useState<{ file: File; preview: string } | null>(null);
  const [removePhoto, setRemovePhoto] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  // Closing = unmounting (removing an open dialog dismisses it), via close() below for ×, 취소 and the
  // backdrop, and via the native "cancel" event for Esc. Not via the "close" event: Chromium fires it on
  // the next animation frame, which never comes while the tab isn't rendering.
  const closeRef = useRef(onClose);
  useEffect(() => { closeRef.current = () => { if (!busy) onClose(); }; });
  useEffect(() => {
    const element = dialog.current!;
    if (!element.open) element.showModal();
    element.querySelector<HTMLInputElement>(".profile-modal-field input")?.focus();  // not the × button
    const cancel = (event: Event) => { event.preventDefault(); closeRef.current(); };
    element.addEventListener("cancel", cancel);
    return () => element.removeEventListener("cancel", cancel);
  }, []);
  const close = () => closeRef.current();
  useEffect(() => () => { if (photo) URL.revokeObjectURL(photo.preview); }, [photo]);

  const preview = photo?.preview ?? (removePhoto ? null : user.avatar_url);
  const trimmed = name.trim();
  const changed = trimmed !== (user.display_name ?? "") || Boolean(photo) || (removePhoto && Boolean(user.avatar_url));

  function choose(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > MAX_INPUT_BYTES) { setError("20MB 이하의 이미지 파일을 선택해 주세요."); return; }
    setError("");
    setRemovePhoto(false);
    setPhoto({ file, preview: URL.createObjectURL(file) });
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!trimmed) { setError("이름을 입력해 주세요."); return; }
    setBusy(true); setError("");
    try {
      let next = user;
      if (trimmed !== (user.display_name ?? "")) next = await updateProfile(trimmed);
      if (photo) next = await uploadAvatar(photo.file);
      else if (removePhoto && user.avatar_url) next = await removeAvatar();
      onSaved(next);
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
    }
  }

  return <dialog ref={dialog} className="profile-modal" aria-labelledby="profile-modal-title"
    onClick={event => { if (event.target === dialog.current) close(); }}>
    <form onSubmit={save}>
      <div className="profile-modal-head">
        <h2 id="profile-modal-title">프로필 수정</h2>
        <button type="button" className="profile-modal-close" aria-label="닫기" disabled={busy} onClick={close}>×</button>
      </div>
      <div className="profile-modal-photo">
        <UserAvatar user={{ ...user, display_name: trimmed || user.display_name }} src={preview} className="profile-modal-avatar" />
        <div className="profile-modal-photo-actions">
          <input ref={fileInput} type="file" accept="image/jpeg,image/png,image/webp" hidden onChange={choose} />
          <button type="button" className="profile-modal-secondary" disabled={busy} onClick={() => fileInput.current?.click()}>사진 변경</button>
          {preview && <button type="button" className="profile-modal-text" disabled={busy} onClick={() => { setPhoto(null); setRemovePhoto(true); }}>사진 삭제</button>}
          <small>JPG, PNG, WEBP · 정사각형으로 잘려요</small>
        </div>
      </div>
      <label className="profile-modal-field">
        <span>NAME <small>{trimmed.length}/{PROFILE_NAME_MAX}</small></span>
        <input value={name} onChange={event => setName(event.target.value)} maxLength={PROFILE_NAME_MAX} required disabled={busy} autoComplete="nickname" />
      </label>
      {error && <p className="api-error" role="alert">{error}</p>}
      <div className="profile-modal-actions">
        <button type="button" className="profile-modal-secondary" disabled={busy} onClick={close}>취소</button>
        <button type="submit" className="photo-action" disabled={busy || !changed || !trimmed}>{busy ? "저장 중…" : "저장"} <span aria-hidden="true">↗</span></button>
      </div>
    </form>
  </dialog>;
}
