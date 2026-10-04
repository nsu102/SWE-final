import type { User } from "../types/api";
import { jsonBody, request } from "./http";

export const getMe = (signal?: AbortSignal) => request<User>("/auth/me", { signal });
export const signIn = (email: string, password: string) => request<User>("/auth/login", jsonBody({ email, password }));
export const signUp = (email: string, password: string) => request<User>("/auth/register", jsonBody({ email, password }));
export const signOut = () => request<void>("/auth/logout", { method: "POST" });
export const requestPasswordReset = (email: string) => request<void>("/auth/reset-request", jsonBody({ email }));
export const resetPassword = (token: string, password: string) => request<User>("/auth/reset", jsonBody({ token, password }));
