/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Prevent dev/build (or multiple dev servers) from corrupting each other's output.
  // - Default build output remains `.next`
  // - Dev can use `NEXT_DIST_DIR=.next-dev-*` via npm scripts
  distDir: process.env.NEXT_DIST_DIR || ".next",
  images: {
    domains: ["avatars.githubusercontent.com", "lh3.googleusercontent.com"],
  },
  async rewrites() {
    return [
      {
        source: "/api/backend/:path*",
        destination: `${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
