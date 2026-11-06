/** @type {import('next').NextConfig} */
const nextConfig = {
  // Dev servers build into .next-dev (scripts/dev.sh) so they never overwrite the .next that
  // the production `next start` (launchd com.ons.nextjs) is serving from.
  distDir: process.env.NEXT_DIST_DIR || ".next",
  env: {
    NEXT_PUBLIC_API_BASE: process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api",
  },
};

module.exports = nextConfig;
