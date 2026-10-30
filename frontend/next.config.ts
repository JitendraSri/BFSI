import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "export",
  trailingSlash: true,
  images: { unoptimized: true },
  // API calls go to NEXT_PUBLIC_API_URL (set to "" in production — same origin)
};

export default nextConfig;
