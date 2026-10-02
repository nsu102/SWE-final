import { proxyKakaoOAuth } from "./kakao-oauth";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  return proxyKakaoOAuth(request, "/api/auth/kakao");
}
