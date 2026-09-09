import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { Consequence, GapTag, Mark } from "@/components/Standing";
import { allGazettes, gazette, missingFrom, thread, threadMembers } from "@/lib/corpus";
import { formatDate, fromSlug, standingOf, toSlug } from "@/lib/standing";

/* One static page per gazette. This is the reason for the framework: 144 pages
 * a crawler can read, where a single-page app offered none. Someone searching
 * for a tax invoice format should land here and learn, without ever having
 * heard of this site, that the document they found was superseded. */

export const dynamicParams = false;

export function generateStaticParams() {
  return allGazettes().map((g) => ({ slug: toSlug(g.no) }));
}

export async function generateMetadata(
  { params }: { params: Promise<{ slug: string }> },
): Promise<Metadata> {
  const { slug } = await params;
  const g = gazette(fromSlug(slug));
  if (!g) return { title: "Not found" };
  const s = standingOf(g);
  // The description leads with standing, because that is what a searcher needs
  // from the snippet before they decide whether to click.
  const lead = s.consequence ? `${s.pill}. ${s.consequence}.` : `${s.pill}.`;
  return {
    title: `${g.no} — ${g.title}`,
    description: `${lead} ${g.summary ?? ""}`.trim().slice(0, 300),
    alternates: { canonical: `/vidhana/gazette/${slug}/` },
  };
}

export default async function GazettePage(
  { params }: { params: Promise<{ slug: string }> },
) {
  const { slug } = await params;
  const g = gazette(fromSlug(slug));
  if (!g) notFound();

  const members = g.thread_id ? threadMembers(g.thread_id) : [g];
  const t = g.thread_id ? thread(g.thread_id) : undefined;
  const missing = missingFrom(members);
  const head = t ? members.find((m) => m.no === t.head_no) : undefined;
  const s = standingOf(g);

  return (
    <article className="mx-auto max-w-[820px] px-6 pb-10 pt-8 md:px-14">
      <Link className="label !opacity-100 underline underline-offset-4" href="/">
        ← Search the corpus
      </Link>

      <div className="mt-6 border-b pb-4" style={{ borderColor: "var(--hair-strong)" }}>
        <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
          <span className="mono text-[17px] font-medium">{g.no}</span>
          <span className="mono text-[12px] opacity-50">
            {formatDate(g.published_date)}
            {g.effective_from && g.effective_from !== g.published_date &&
              ` · effective ${formatDate(g.effective_from)}`}
          </span>
          <span className="grow" />
          <Mark g={g} />
        </div>
        <h1 className="mt-3 max-w-[680px] text-[30px] leading-[1.22]">{g.title}</h1>
        <Consequence g={g} />
      </div>

      {g.summary && (
        <p className="mt-5 max-w-[660px] text-[17px] leading-[1.6]">{g.summary}</p>
      )}
      {g.confidence && g.confidence !== "high" && (
        <p className="mt-3 max-w-[660px] text-[13.5px] italic opacity-60">
          This summary was generated with {g.confidence} confidence. Read the gazette before
          relying on it.
        </p>
      )}

      <p className="mt-6 flex flex-wrap items-center gap-5">
        <a className="text-[16px] font-semibold link" href={g.source_url} rel="noopener">
          Open the gazette PDF →
        </a>
        {head && head.no !== g.no && (
          <Link className="text-[16px] italic link" href={`/gazette/${toSlug(head.no)}/`}>
            Go to {head.no}, the current document →
          </Link>
        )}
      </p>

      <div className="mt-5 flex flex-wrap items-center gap-[10px]">
        <span className="tag">{g.subject}</span>
        {t ? <span className="tag">{t.size} in this rule</span> : <span className="tag">standalone</span>}
        {g.source !== "ird-listing" && (
          <span className="tag" title="Not in the IRD listing; recovered from the Internet Archive">
            recovered
          </span>
        )}
        <GapTag missing={missing} />
      </div>

      {missing.length > 0 && (
        <p className="mt-5 border-l-2 border-dashed py-1 pl-4 text-[14.5px] italic leading-relaxed"
           style={{ borderColor: "var(--hair-strong)" }}>
          <strong className="not-italic font-semibold">This rule’s history is incomplete.</strong>{" "}
          <span className="mono not-italic text-[13.5px]">{missing.join(", ")}</span>{" "}
          {missing.length > 1 ? "are" : "is"} referenced by a document we hold but missing from the
          IRD listing, so a change made by a gazette we do not hold would not appear below.
        </p>
      )}

      {t && (
        <>
          <h2 className="label mt-10">The rule, in sequence</h2>
          <ol className="mt-4 border-l pl-6" style={{ borderColor: "var(--hair-strong)" }}>
            {members.map((m) => {
              const isHead = m.no === t.head_no;
              return (
                <li key={m.no} className="relative py-[11px]">
                  <span className="absolute -left-[30px] top-[19px] h-[9px] w-[9px] rounded-full"
                        style={isHead
                          ? { background: "var(--ink)" }
                          : { border: "1.5px solid var(--ink)", background: "var(--paper)" }} />
                  <div className="flex flex-wrap items-baseline gap-x-[13px] gap-y-1">
                    <Link className="mono text-[14px] link"
                          style={{ fontWeight: isHead ? 600 : 400 }}
                          href={`/gazette/${toSlug(m.no)}/`}>{m.no}</Link>
                    <span className="mono text-[11.5px] opacity-50">
                      {formatDate(m.published_date)}
                    </span>
                    <span className="text-[14.5px] italic opacity-80">
                      {standingOf(m).kind === "current" ? "the rule now"
                        : standingOf(m).kind === "rescinded" ? "rescinded" : "superseded"}
                    </span>
                    {m.no === g.no && <span className="tag not-italic">you are here</span>}
                  </div>
                  <p className="mt-1 max-w-[600px] text-[14px] opacity-[.62]">{m.title}</p>
                </li>
              );
            })}
          </ol>
          <p className="mt-4">
            <Link className="text-[15px] italic link" href={`/rule/${t.thread_id}/`}>
              See this rule on its own page →
            </Link>
          </p>
        </>
      )}

      <div className="mt-10 grid gap-8 border-t pt-6 md:grid-cols-2"
           style={{ borderColor: "var(--hair)" }}>
        <div>
          <h2 className="label">Who this affects</h2>
          <p className="mt-2 text-[16px]">
            {g.audience.length ? g.audience.join("; ") : "Not stated."}
          </p>
          <p className="mt-2 text-[13px] italic opacity-60">
            Inferred from the enabling Act — gazettes rarely state who they bind, and the model
            may only narrow within the Act’s known audiences.
          </p>
        </div>
        <div>
          <h2 className="label">Enabling Act</h2>
          <p className="mt-2 text-[16px]">{g.enabling_act ?? "Not parsed."}</p>
          {g.source !== "ird-listing" && (
            <p className="mt-2 text-[13px] italic opacity-60">
              Recovered from the Internet Archive — this gazette is not in the IRD listing.
            </p>
          )}
        </div>
      </div>
    </article>
  );
}
