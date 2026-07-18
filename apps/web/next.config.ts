import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  async rewrites() {
    const target = process.env.ORBIT_API_INTERNAL_BASE ?? "http://127.0.0.1:8000";
    return [{ source: "/orbit-api/:path*", destination: `${target}/:path*` }];
  },
};

export default nextConfig;
