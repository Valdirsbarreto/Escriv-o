import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1",
  },
  turbopack: {
    resolveAlias: {
      canvas: "./src/lib/canvas-empty.ts",
    },
  },
};

export default nextConfig;
