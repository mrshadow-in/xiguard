const path = require("path");

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  webpack: (config) => {
    config.resolve = config.resolve || {};
    config.resolve.alias = {
      ...(config.resolve.alias || {}),
      "@": path.resolve(__dirname, "src"),
    };
    return config;
  },
  async rewrites() {
    const apiBase = process.env.BACKEND_INTERNAL_URL || "http://api:8000";
    return [
      { source: "/api/:path*", destination: `${apiBase}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
