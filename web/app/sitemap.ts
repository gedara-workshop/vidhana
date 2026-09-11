import type { MetadataRoute } from "next";

import { allGazettes, allThreads } from "@/lib/corpus";
import { sitemapEntries } from "@/lib/site";

/* Emitted at build time into the static export. Every page this app renders is
 * pre-rendered precisely so a crawler can read it; without a sitemap, nothing
 * tells one that 164 deep pages exist on a domain with no inbound links.
 *
 * The logic lives in `lib/site.ts` so it can be unit-tested — this file only
 * adapts it to Next's metadata shape. */

export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  return sitemapEntries(allGazettes(), allThreads()).map((e) => ({
    url: e.url,
    lastModified: new Date(`${e.lastModified}T00:00:00Z`),
    changeFrequency: e.changeFrequency,
    priority: e.priority,
  }));
}
