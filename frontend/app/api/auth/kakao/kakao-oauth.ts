/** Server-only Kakao OAuth bridge for Next.js route handlers. */
const backendUrl = () => (process.env.BACKEND_URL || "http://127.0.0.1:8000").replace(/\/$/, "");

function responseHeaders(source: Headers): Headers {
  const headers = new Headers();
  for (const name of ["cache-control", "location"]) {
    const value = source.get(name);
    if (value) headers.set(name, value);
  }
  // get("set-cookie") would comma-join the session and state cookies into one broken header.
  for (const cookie of source.getSetCookie()) headers.append("set-cookie", cookie);
  return headers;
}

export async function proxyKakaoOAuth(request: Request, path: "/api/auth/kakao" | "/api/auth/kakao/callback") {
  const incoming = new URL(request.url);
  const upstream = await fetch(`${backendUrl()}${path}${incoming.search}`, {
    method: "GET",
    headers: {
      cookie: request.headers.get("cookie") ?? "",
      "x-forwarded-host": incoming.host,
      "x-forwarded-proto": incoming.protocol.replace(":", ""),
    },
    cache: "no-store",
    redirect: "manual",
  });
  return new Response(null, { status: upstream.status, headers: responseHeaders(upstream.headers) });
}
