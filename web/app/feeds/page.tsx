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
    <article className="mx-auto max-w-[820px] px-6 pb-10 pt-8 md:px-14">
      <Link className="label !opacity-100 underline underline-offset-4" href="/">
        ← Search the corpus
      </Link>
      <h1 className="mt-6 text-[34px] leading-tight">Feeds</h1>
      <p className="mt-3 max-w-[620px] text-[17px] leading-[1.6]">
        Atom feeds, updated nightly. Each entry says what a gazette does, who it affects, and
        which document is currently the rule — and where a rule’s history has a hole, it says
        that too.
      </p>

      <ul className="mt-8 border-t" style={{ borderColor: "var(--hair-strong)" }}>
        <li className="entry">
          <a className="flex items-baseline justify-between gap-4 py-[14px]"
             href={`${BASE}/feeds/all.xml`}>
            <span className="text-[19px]">Everything</span>
            <span className="mono text-[12px] opacity-50">{counts.gazettes} gazettes</span>
          </a>
        </li>
        {subjects.map(([s, n]) => (
          <li key={s} className="entry">
            <a className="flex items-baseline justify-between gap-4 py-[14px]"
               href={`${BASE}/feeds/${s}.xml`}>
              <span className="text-[19px]">{s}</span>
              <span className="mono text-[12px] opacity-50">{n}</span>
            </a>
          </li>
        ))}
      </ul>

      <p className="mt-8 max-w-[640px] text-[14px] italic leading-relaxed opacity-[.68]">
        Feeds were chosen over email deliberately: at three to six gazettes a year an inbox
        pipeline is mostly unused plumbing, and a feed holds no personal data, needs no server,
        and composes with everything else later.
      </p>
    </article>
  );
}
