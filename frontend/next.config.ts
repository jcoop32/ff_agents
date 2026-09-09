import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // Tailscale mesh and internal cluster IPs for homelab dev server
  allowedDevOrigins: [
    "100.*",
    "10.*",
    "localhost:3000",
    "127.0.0.1:3000",
    "localhost:30081",
    "localhost:31081"
  ],
  async rewrites() {
    const backendUrl =
      process.env.INTERNAL_API_URL ||
      "http://gridiron-service.gridiron-ai.svc.cluster.local:8000";
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
