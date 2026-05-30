/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  output: "standalone",
  async rewrites() {
    const apiBase = process.env.BACKEND_INTERNAL_URL || "http://api:8000";
    return [
      { source: "/api/:path*", destination: `${apiBase}/api/:path*` },
    ];
  },
};

module.exports = nextConfig;
