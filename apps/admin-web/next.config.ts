import type { NextConfig } from "next";

// INT-351 — the admin-web shell. No image optimiser (it is the one Next.js
// feature that pulls a native image library, and the console renders no
// image), no `x-powered-by` banner, strict mode on.
const config: NextConfig = {
  poweredByHeader: false,
  reactStrictMode: true,
  images: { unoptimized: true },
};

export default config;
