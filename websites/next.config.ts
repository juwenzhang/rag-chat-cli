import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

// Keep Vercel deployments framework-native by default. Self-hosted Docker
// builds set this flag to produce `.next/standalone/server.js`.
if (process.env.NEXT_OUTPUT_STANDALONE === "true") {
  nextConfig.output = "standalone";
}

export default nextConfig;
