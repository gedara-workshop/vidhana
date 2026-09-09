import type { Metadata } from "next";
import Link from "next/link";

import { corpus, facetCounts } from "@/lib/corpus";

const BASE = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "Feeds",
  description:
    "Atom feeds of what changed in the Sri Lankan Inland Revenue gazettes — what each " +
    "gazette does, who it affects, and which document is currently the rule.",
};

/* The feed index. The XML files themselves are written by `vidhana feed` and
 * copied into the build output untouched: people are subscribed to those URLs,
 * and a feed's whole job is to be a stable address. */
export default function FeedsPage() {
  const { counts } = corpus();
  const subjects = facetCounts().subject;

  return (
    <main className="mx-auto max-w-3xl px-6 py-10">
      <Link className="link text-[13px]" href="/">← Search the corpus</Link>
      <h1 className="mt-4 text-[30px] font-bold leading-tight tracking-tight">Feeds</h1>
      <p className="mt-3 text-[15px] leading-relaxed" style={{ color: "var(--dim)" }}>
        Atom feeds, updated nightly. Each entry says what a gazette does, who it affects, and
        which document is currently the rule — and where a rule’s history has a hole, it says
        that too.
      </p>

      <ul className="mt-8">
        <li style={{ borderTop: "1px solid var(--line)" }}>
          <a className="flex items-baseline justify-between gap-4 px-1 py-3"
             href={`${BASE}/feeds/all.xml`}>
            <span className="font-medium">Everything</span>
            <span className="font-mono text-[12px]" style={{ color: "var(--dim)" }}>
              {counts.gazettes} gazettes
            </span>
          </a>
        </li>
        {subjects.map(([s, n]) => (
          <li key={s} style={{ borderTop: "1px solid var(--line)" }}>
            <a className="flex items-baseline justify-between gap-4 px-1 py-3"
               href={`${BASE}/feeds/${s}.xml`}>
              <span className="font-medium">{s}</span>
              <span className="font-mono text-[12px]" style={{ color: "var(--dim)" }}>{n}</span>
            </a>
          </li>
        ))}
      </ul>

      <p className="mt-8 text-[12.5px] leading-relaxed" style={{ color: "var(--dim)" }}>
        Feeds were chosen over email deliberately: at three to six gazettes a year an inbox
        pipeline is mostly unused plumbing, and a feed holds no personal data, needs no server,
        and composes with everything else later.
      </p>
    </main>
  );
}
