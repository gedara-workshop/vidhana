import type { NextConfig } from "next";

/* Static export. Every gazette and every rule is pre-rendered at build time,
 * which is the whole reason for the framework: the corpus is 192 pages a
 * crawler can read, where the previous single-page app offered none.
 *
 * `output: "export"` is a deployment choice, not an architectural one — the app
 * uses generateStaticParams and server components throughout, so moving to a
 * Node host for ISR or route handlers later means changing this file, not the
 * application. Nothing here depends on being static.
 *
 * basePath is set for the project Pages site (gedara-workshop.github.io/vidhana)
 * and overridable so a custom domain needs no code change.
 */
const basePath = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

const nextConfig: NextConfig = {
  output: "export",
  basePath,
  trailingSlash: true,          // Pages serves /foo/ as /foo/index.html
  images: { unoptimized: true },
  reactStrictMode: true,
  typedRoutes: true,
  env: { NEXT_PUBLIC_BASE_PATH: basePath },
};

export default nextConfig;
