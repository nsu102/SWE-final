import { AVATAR_UPLOAD_SIDE } from "../constants/look-find";
import type { User } from "../types/api";
import { downscaleImage } from "../utils/image";
import { jsonBody, request } from "./http";

export const updateProfile = (displayName: string) => request<User>("/auth/me", jsonBody({ display_name: displayName }, "PATCH"));

export async function uploadAvatar(file: File) {
  const form = new FormData();
  form.append("image", await downscaleImage(file, AVATAR_UPLOAD_SIDE));
  return request<User>("/auth/me/avatar", { method: "PUT", body: form });
}

export const removeAvatar = () => request<User>("/auth/me/avatar", { method: "DELETE" });
