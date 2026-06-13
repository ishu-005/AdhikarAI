/** @type {import('next').NextConfig} */

// Vercel is the canonical frontend host. STATIC_EXPORT remains available for
// local/static experiments, but production uses the native Next.js build.
const staticExport = process.env.STATIC_EXPORT === "true";

const nextConfig = {
  ...(staticExport ? { output: "export" } : {}),
  images: { unoptimized: true },
  trailingSlash: false,
};

module.exports = nextConfig;
