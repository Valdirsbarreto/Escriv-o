import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Variável de ambiente pública para a URL do backend
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1",
  },
};

export default nextConfig;
