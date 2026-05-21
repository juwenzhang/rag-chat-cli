import type { NextConfig } from "next";

const isStandalone = process.env.NEXT_OUTPUT_STANDALONE === "true";

const securityHeaders = [
  {
    key: "X-Frame-Options",
    value: "DENY",
  },
  {
    key: "X-Content-Type-Options",
    value: "nosniff",
  },
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin",
  },
  {
    key: "Permissions-Policy",
    value: [
      "camera=()",
      "microphone=()",
      "geolocation=()",
      "payment=()",
      "usb=()",
      "magnetometer=()",
      "gyroscope=()",
      "accelerometer=()",
    ].join(", "),
  },
];

const nextConfig: NextConfig = {
  compress: true,
  poweredByHeader: false,

  async headers() {
    return [
      {
        source: "/:path*",
        headers: securityHeaders,
      },
    ];
  },
};

// Keep Vercel deployments framework-native by default. Self-hosted Docker
// builds set this flag to produce `.next/standalone/server.js`.
if (isStandalone) {
  nextConfig.output = "standalone";
}

export default nextConfig;
