import type { NextConfig } from "next";
import { PHASE_DEVELOPMENT_SERVER } from "next/constants";

export default function nextConfig(phase: string): NextConfig {
  if (phase === PHASE_DEVELOPMENT_SERVER) {
    return {
      experimental: { proxyTimeout: 180_000 },
      async rewrites() {
        const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
        return [
          { source: "/api/:path*", destination: `${backend}/api/:path*` },
          { source: "/media/:path*", destination: `${backend}/media/:path*` },
        ];
      },
    };
  }
  return { output: "export", images: { unoptimized: true } };
}
