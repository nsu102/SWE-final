import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // The first search loads the ML models (tens of seconds); the default 30s proxy timeout would cut it off.
  experimental: { proxyTimeout: 180_000 },
  async rewrites() {
    const backend = process.env.BACKEND_URL || "http://127.0.0.1:8000";
    return [
      { source: "/api/:path*", destination: `${backend}/api/:path*` },
      { source: "/media/:path*", destination: `${backend}/media/:path*` },
    ];
  },
};

export default nextConfig;
