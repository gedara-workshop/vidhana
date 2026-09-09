import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";


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
    <div className="h-full overflow-y-auto">
      <article className="mx-auto max-w-3xl px-5 py-6">
        <Link className="navlink -ml-[10px]" href="/">← Back to search</Link>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <span className="mono text-[15px] font-semibold">{g.no}</span>
          <span className={`state state-${s.kind}`}>{s.pill}</span>
          <span className="grow" />
          <span className="mono text-[11px]" style={{ color: "var(--faint)" }}>
            {formatDate(g.published_date)}
          </span>
        </div>

        <h1 className="mt-2 text-[22px] font-bold leading-snug tracking-tight">{g.title}</h1>
        {s.consequence && (
          <p className="mt-[6px] text-[13px] font-medium"
             style={{ color: s.kind === "rescinded" ? "var(--res)" : "var(--sup)" }}>
            {s.consequence}
          </p>
        )}

        <div className="mt-3 flex flex-wrap items-center gap-[6px]">
          <span className="tag">{g.subject}</span>
          {t && <span className="tag">{t.size} in rule</span>}
          {g.confidence && g.confidence !== "high" && (
            <span className="tag">{g.confidence} confidence</span>
          )}
          {g.source !== "ird-listing" && (
            <span className="tag" title="Not in the IRD listing; recovered from the Internet Archive">
              recovered
            </span>
          )}
          {missing.length > 0 && <span className="tag tag-warn">history incomplete</span>}
        </div>

        <div className="mt-4 flex flex-wrap gap-2">
          <a className="btn btn-primary" href={g.source_url} rel="noopener">Open the gazette PDF</a>
          {head && head.no !== g.no && (
            <Link className="btn" href={`/gazette/${toSlug(head.no)}/`}>
              Go to {head.no}, current
            </Link>
          )}
          {t && <Link className="btn" href={`/rule/${t.thread_id}/`}>See the whole rule</Link>}
        </div>

        {g.summary && (
          <div className="mt-5 rounded-[8px] border p-4" style={{ borderColor: "var(--line)",
               background: "var(--panel)" }}>
            <p className="sec">Summary</p>
            <p className="mt-2 text-[14px] leading-relaxed">{g.summary}</p>
            {g.confidence && g.confidence !== "high" && (
              <p className="mt-2 text-[11.5px]" style={{ color: "var(--sup)" }}>
                Generated with {g.confidence} confidence. Read the gazette before relying on it.
              </p>
            )}
          </div>
        )}

        {missing.length > 0 && (
          <p className="mt-3 rounded-[8px] px-4 py-3 text-[12.5px] leading-relaxed"
             style={{ background: "var(--sup-bg)", color: "var(--sup)" }}>
            <strong>This rule’s history is incomplete.</strong>{" "}
            <span className="mono">{missing.join(", ")}</span>{" "}
            {missing.length > 1 ? "are" : "is"} referenced by a document we hold but missing from
            the IRD listing, so a change made by a gazette we do not hold would not appear below.
          </p>
        )}

        <div className="mt-5 grid gap-3 sm:grid-cols-2">
          <div className="rounded-[8px] border p-4" style={{ borderColor: "var(--line)" }}>
            <p className="sec">Who this affects</p>
            <p className="mt-2 text-[13px]">
              {g.audience.length ? g.audience.join("; ") : "Not stated."}
            </p>
            <p className="mt-2 text-[11.5px] leading-relaxed" style={{ color: "var(--faint)" }}>
              Inferred from the enabling Act — gazettes rarely state who they bind, and the model
              may only narrow within the Act’s known audiences.
            </p>
          </div>
          <div className="rounded-[8px] border p-4" style={{ borderColor: "var(--line)" }}>
            <p className="sec">Enabling Act</p>
            <p className="mt-2 text-[13px]">{g.enabling_act ?? "Not parsed."}</p>
            <p className="mt-2 text-[11.5px]" style={{ color: "var(--faint)" }}>
              Effective {formatDate(g.effective_from) || "—"}
            </p>
          </div>
        </div>

        {t && (
          <>
            <p className="sec mt-6 mb-2">The rule, over time · {members.length} documents</p>
            <div className="overflow-hidden rounded-[8px] border" style={{ borderColor: "var(--line)" }}>
              {members.map((m) => {
                const ms = standingOf(m);
                const here = m.no === g.no;
                return (
                  <Link key={m.no} href={`/gazette/${toSlug(m.no)}/`}
                        className="block border-b px-4 py-[10px] last:border-0 hover:bg-[var(--raised)]"
                        style={{ borderColor: "var(--line-soft)",
                                 background: here ? "var(--raised)" : undefined }}>
                    <span className="flex flex-wrap items-center gap-2">
                      <span className="mono text-[12px] font-semibold">{m.no}</span>
                      <span className={`state state-${ms.kind}`}>{ms.pill}</span>
                      {here && <span className="tag">you are here</span>}
                      <span className="grow" />
                      <span className="mono text-[10.5px]" style={{ color: "var(--faint)" }}>
                        {formatDate(m.published_date)}
                      </span>
                    </span>
                    <span className="clamp-1 mt-[3px] block text-[12.5px]"
                          style={{ color: "var(--dim)" }}>{m.title}</span>
                  </Link>
                );
              })}
            </div>
          </>
        )}

        <p className="mt-6 text-[11.5px] leading-relaxed" style={{ color: "var(--faint)" }}>
          Summaries are machine-written; the gazette is the source of truth. “In force” means not
          rescinded by another gazette in this corpus — weaker than a legal determination. Not
          legal advice.
        </p>
      </article>
    </div>
  );
}
