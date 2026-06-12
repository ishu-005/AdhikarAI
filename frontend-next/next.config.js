/** @type {import('next').NextConfig} */

// Two deploy modes:
//  • Vercel (default): native Next.js build. The browser calls the backend
//    directly via NEXT_PUBLIC_API_BASE (set in Vercel project env).
//  • Single-container (Docker/HF Spaces): set STATIC_EXPORT=true so `next build`
//    emits a static site to ./out that FastAPI serves at "/".
const staticExport = process.env.STATIC_EXPORT === "true";

const nextConfig = {
  ...(staticExport ? { output: "export" } : {}),
  images: { unoptimized: true },
  trailingSlash: false,
};

module.exports = nextConfig;
