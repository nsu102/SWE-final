import { ApiError } from "../apis/http";

export const errorMessage = (error: unknown) => error instanceof Error ? error.message : "요청을 처리하지 못했습니다.";
export const isUnauthorized = (error: unknown) => error instanceof ApiError && error.status === 401;
