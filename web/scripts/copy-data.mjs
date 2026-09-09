/* Copy the exported corpus into public/ before dev or build.
 *
 * The export lives in docs/data because the Python pipeline writes it there and
 * the nightly job commits it. Copying rather than symlinking keeps the Next
 * build self-contained — a CI checkout has no symlink target problems — and
 * makes the dependency explicit: no corpus, no build. */
import { copyFileSync, existsSync, mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const from = join(here, "..", "..", "docs", "data");
const to = join(here, "..", "public", "data");

if (!existsSync(join(from, "index.json"))) {
  console.error(
    "No corpus at docs/data/index.json.\n" +
    "Run `python3 -m vidhana export-web` from the repository root first.");
  process.exit(1);
}
mkdirSync(to, { recursive: true });
for (const f of ["index.json", "bodies.json"]) copyFileSync(join(from, f), join(to, f));
console.log("corpus copied into public/data");
