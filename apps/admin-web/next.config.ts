import type { NextConfig } from "next";

// INT-351 — the admin-web shell. No image optimiser (it is the one Next.js
// feature that pulls a native image library, and the console renders no
// image), no `x-powered-by` banner, strict mode on.
// INT-599 — standalone output: `next build` writes server.js and copies in only
// the package files the server's trace reaches, so the staging image's runtime
// stage carries that and the static assets, never the build tooling
// (infra/staging/Dockerfile.admin-web).
const config: NextConfig = {
  output: "standalone",
  poweredByHeader: false,
  reactStrictMode: true,
  images: { unoptimized: true },
};

export default config;
