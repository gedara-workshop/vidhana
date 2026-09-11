/* Assert the sitemap and the export agree.
 *
 * The failure this exists to catch is not a broken build — it is a silent one.
 * Add a route and forget `lib/site.ts`, and the page ships, renders, and is
 * never crawled. Nothing goes red. So the check is both directions: every URL
 * in the sitemap resolves to a rendered page, and every rendered page appears
 * in the sitemap.
 *
 * Run from web/ after a build: `node scripts/check-sitemap.mjs`
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative, sep } from "node:path";

const OUT = new URL("../out/", import.meta.url).pathname;
const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

/* Rendered but deliberately unlisted. A 404 page is not content. */
const UNLISTED = new Set(["/404/"]);

function fail(msg) {
  console.error(`✗ ${msg}`);
  process.exitCode = 1;
}

const xml = readFileSync(join(OUT, "sitemap.xml"), "utf8");
const locs = [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map((m) => m[1]);
if (locs.length === 0) fail("sitemap.xml lists no URLs");

/** Every directory holding an index.html, as a site-absolute path. */
function rendered(dir = OUT, found = new Set()) {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.isDirectory()) rendered(join(dir, e.name), found);
    else if (e.name === "index.html") {
      const rel = relative(OUT, dir).split(sep).join("/");
      found.add(rel ? `/${rel}/` : "/");
    }
  }
  return found;
}

const pages = rendered();
const listed = new Set();

for (const loc of locs) {
  if (!loc.startsWith("https://")) { fail(`not an absolute URL: ${loc}`); continue; }
  if (!loc.endsWith("/") && !loc.endsWith(".xml")) fail(`missing trailing slash: ${loc}`);

  const { pathname } = new URL(loc);
  if (BASE && !pathname.startsWith(`${BASE}/`)) { fail(`outside basePath ${BASE}: ${loc}`); continue; }
  const path = pathname.slice(BASE.length) || "/";

  if (listed.has(path)) fail(`listed twice: ${loc}`);
  listed.add(path);

  try {
    statSync(join(OUT, path, "index.html"));
  } catch {
    fail(`sitemap lists ${loc}, which the export did not render`);
  }
}

for (const p of [...pages].sort()) {
  if (UNLISTED.has(p)) continue;
  if (!listed.has(p)) fail(`${p} is rendered but missing from the sitemap — add it in lib/site.ts`);
}

const robots = readFileSync(join(OUT, "robots.txt"), "utf8");
if (!robots.includes("Sitemap: ")) fail("robots.txt does not name the sitemap");

if (process.exitCode) process.exit(1);
console.log(`✓ sitemap and export agree: ${listed.size} URLs, ${pages.size} rendered pages`);
