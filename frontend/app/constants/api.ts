// Same-origin API (next.config.ts proxies /api in dev; CloudFront routes /api/* in production).
export const API_BASE = "/api";
// Network errors and gateway errors (e.g. a Lambda cold start) are retried with these backoffs,
// but only for idempotent methods: a retried POST could run twice on the server.
export const RETRY_DELAYS_MS = [400, 1200];
export const RETRYABLE_STATUS = [502, 503, 504];
export const IDEMPOTENT_METHODS = ["GET", "HEAD", "PUT", "DELETE"];
// A 401 from these means "wrong credentials / no session", not "access token expired".
export const NO_REFRESH_PATHS = ["/auth/login", "/auth/register", "/auth/refresh", "/auth/logout", "/auth/reset", "/auth/reset-request"];
export const SEARCH_LIMIT = 24;
