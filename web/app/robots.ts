import type { MetadataRoute } from "next";

import { url } from "@/lib/site";

/* Emitted into the static export as robots.txt.
 *
 * Caveat worth knowing before trusting this file: robots.txt is only honoured
 * at the *origin* root. This is a project Pages site, so the file lands at
 * /vidhana/robots.txt and https://gedara-workshop.github.io/robots.txt is a
 * 404 that this repo cannot fix — that path belongs to a
 * `gedara-workshop.github.io` repo which does not exist.
 *
 * So this file does not, on its own, get the sitemap discovered. The sitemap is
 * submitted to Search Console directly. Keep the file anyway: it costs nothing,
 * it becomes authoritative the moment the site moves to a custom domain or an
 * org root page, and it documents the intent in the repo instead of only in a
 * console someone else cannot see.
 *
 * Everything is crawlable. There is no user data, no search-result permutation
 * worth excluding, and the corpus is public law.
 */

export const dynamic = "force-static";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [{ userAgent: "*", allow: "/" }],
    // No `host` directive: it takes a bare hostname, and on a project Pages
    // site the only honest value would include the /vidhana path, which is not
    // a legal value for it.
    sitemap: url("/sitemap.xml"),
  };
}
