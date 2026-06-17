/** @type {import('next').NextConfig} */
const nextConfig = {
  // Allow the Claude preview dev server to use a separate build dir so it
  // never clobbers the production `.next` served by `next start`.
  distDir: process.env.NEXT_DIST_DIR || '.next',
  async rewrites() {
    const apiBase = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
    return [
      {
        source: '/api/:path*',
        destination: `${apiBase}/api/:path*`,
      },
    ]
  },
}

export default nextConfig
