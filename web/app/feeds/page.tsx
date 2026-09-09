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
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-3xl px-5 py-6">
        <h1 className="text-[20px] font-bold tracking-tight">Feeds</h1>
        <p className="mt-1 max-w-[600px] text-[13px]" style={{ color: "var(--dim)" }}>
          Atom feeds, updated nightly. Each entry says what a gazette does, who it affects and
          which document is currently the rule — and where a rule’s history has a hole, it says
          that too.
        </p>

        <div className="mt-5 overflow-hidden rounded-[8px] border" style={{ borderColor: "var(--line)" }}>
          <a className="flex items-center justify-between gap-4 border-b px-4 py-3 hover:bg-[var(--raised)]"
             style={{ borderColor: "var(--line-soft)" }} href={`${BASE}/feeds/all.xml`}>
            <span className="text-[13.5px] font-medium">Everything</span>
            <span className="mono text-[11.5px]" style={{ color: "var(--faint)" }}>
              {counts.gazettes} gazettes
            </span>
          </a>
          {subjects.map(([name, n]) => (
            <a key={name} className="flex items-center justify-between gap-4 border-b px-4 py-3 last:border-0 hover:bg-[var(--raised)]"
               style={{ borderColor: "var(--line-soft)" }} href={`${BASE}/feeds/${name}.xml`}>
              <span className="text-[13.5px]">{name}</span>
              <span className="mono text-[11.5px]" style={{ color: "var(--faint)" }}>{n}</span>
            </a>
          ))}
        </div>

        <p className="mt-4 max-w-[620px] text-[11.5px] leading-relaxed" style={{ color: "var(--faint)" }}>
          Feeds were chosen over email deliberately: at three to six gazettes a year an inbox
          pipeline is mostly unused plumbing, and a feed holds no personal data, needs no server,
          and composes with everything else later.
        </p>
      </div>
    </div>
  );
}
