/* Assert the sitemap and the export agree.
 *
 * The failure this exists to catch is not a broken build — it is a silent one.
 * Add a route and forget `lib/site.ts`, and the page ships, renders, and is
 * never crawled. Nothing goes red. So the check is both directions: every URL
 * in the sitemap resolves to a rendered page, and every rendered page appears
 * in the sitemap.
 *
 * Redirect pages are the exception, and are checked harder rather than
 * skipped. A static host cannot send a 301, so an alias such as
 * /rule/2500-106/ is a page carrying a zero-second refresh. Each one must be
 * absent from the sitemap, marked noindex, and land in one hop on a real page
 * that *is* listed — a redirect to a redirect, or to nothing, fails.
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

const REFRESH = /<meta http-equiv="refresh" content="0;url=([^"]+)"/;

/** Redirect pages, as site path -> target site path. */
const redirects = new Map();
for (const p of pages) {
  const html = readFileSync(join(OUT, p, "index.html"), "utf8");
  const m = html.slice(0, html.indexOf("</head>")).match(REFRESH);
  if (!m) continue;
  if (!m[1].startsWith(`${BASE}/`)) { fail(`${p} redirects outside basePath: ${m[1]}`); continue; }
  redirects.set(p, m[1].slice(BASE.length));
  if (!/<meta name="robots" content="noindex"/.test(html)) fail(`${p} redirects but is indexable`);
}

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
  if (redirects.has(p)) {
    const to = redirects.get(p);
    if (listed.has(p)) fail(`sitemap lists ${p}, which is a redirect to ${to}`);
    if (redirects.has(to)) fail(`${p} redirects to ${to}, which redirects again`);
    else if (!listed.has(to)) fail(`${p} redirects to ${to}, which is not a listed page`);
    continue;
  }
  if (!listed.has(p)) fail(`${p} is rendered but missing from the sitemap — add it in lib/site.ts`);
}

const robots = readFileSync(join(OUT, "robots.txt"), "utf8");
if (!robots.includes("Sitemap: ")) fail("robots.txt does not name the sitemap");

if (process.exitCode) process.exit(1);
console.log(`✓ sitemap and export agree: ${listed.size} URLs listed, ` +
            `${redirects.size} redirects each landing on one, ${pages.size} rendered pages`);
