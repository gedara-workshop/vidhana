import type { Metadata } from "next";
import Link from "next/link";

import { ScopeNote } from "@/components/Scope";
import { health } from "@/lib/corpus";
import { formatDate } from "@/lib/standing";

/* The corpus, audited in public.
 *
 * The site asks people to act on what it says about the law, so it shows its
 * own error rate, names the document it knows is missing, and says when it was
 * last built. Everything here is read from docs/data/health.json, which the
 * pipeline writes; nothing on this page is computed twice.
 *
 * The build time is stamped here rather than in the data file. health.json is
 * committed, and a per-run timestamp in it would make the nightly job commit
 * every night — the history is a record of the law changing, not of the
 * workflow running. */

export const metadata: Metadata = {
  title: "Corpus health",
  description:
    "How complete and how accurate this corpus is: validation scores against " +
    "deterministically derived fields, parse warnings, documents that needed OCR, " +
    "and the gazettes referenced but not held.",
  alternates: { canonical: "/vidhana/health/" },
};

const BUILT_AT = new Date().toISOString().slice(0, 10);

const FIELD_LABEL: Record<string, string> = {
  effective_date: "Effective date",
  enabling_act: "Enabling Act",
  authority: "Signatory",
  audience_grounded: "Audience stayed in scope",
};

function Row({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-2 border-b px-4 py-2.5 last:border-0"
         style={{ borderColor: "var(--line-soft)" }}>
      <span className="text-[13px]">{label}</span>
      <span className="grow" />
      <span className="mono text-[12.5px] font-semibold">{value}</span>
      {note && <span className="mono w-full text-[11px]" style={{ color: "var(--faint)" }}>{note}</span>}
    </div>
  );
}

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-6">
      <p className="sec mb-2">{title}</p>
      <div className="overflow-hidden rounded-[8px] border" style={{ borderColor: "var(--line)" }}>
        {children}
      </div>
    </section>
  );
}

export default function HealthPage() {
  const h = health();
  const { corpus, validation, missing, answers } = h;
  const graded = validation.fields.reduce((n, f) => n + f.compared, 0);
  const agreed = validation.fields.reduce((n, f) => n + f.agreed, 0);

  return (
    <div className="h-full overflow-y-auto">
      <article className="mx-auto max-w-3xl px-5 py-6">
        <h1 className="text-[20px] font-bold tracking-tight">Corpus health</h1>
        <p className="mt-1 max-w-[640px] text-[13px]" style={{ color: "var(--dim)" }}>
          What this corpus knows about its own condition — how much of it is checked, what
          disagrees, and what is missing. Published because the site asks you to act on what it
          says about the law.
        </p>
        <ScopeNote className="mt-2 max-w-[640px]" />

        <Panel title="The corpus">
          <Row label="Gazettes held" value={String(corpus.gazettes)}
               note={`${formatDate(corpus.first)} — ${formatDate(corpus.last)}`} />
          <Row label="From the IRD's published listing" value={String(corpus.listed)} />
          <Row label="Recovered from the Internet Archive" value={String(corpus.recovered)}
               note="missing from the IRD listing; marked as recovered wherever they appear" />
          <Row label="Rescinded" value={String(corpus.rescinded)} />
          <Row label="Rules" value={String(corpus.rules)}
               note={corpus.rules_with_holes
                 ? `${corpus.rules_with_holes} has a hole in its history and says so on its page`
                 : "every rule's history is complete"} />
        </Panel>

        <Panel title="Model accuracy, graded against fields derived by rule">
          {validation.fields.map((f) => (
            <Row key={f.field} label={FIELD_LABEL[f.field] ?? f.field}
                 value={`${f.agreed}/${f.compared}`}
                 note={f.compared ? `${Math.round((f.agreed / f.compared) * 100)}% agreement` : "nothing to compare"} />
          ))}
        </Panel>
        <p className="mt-2 text-[11.5px] leading-relaxed" style={{ color: "var(--faint)" }}>
          {agreed === graded
            ? `All ${graded} comparisons agree.`
            : `${graded - agreed} of ${graded} comparisons disagree.`}{" "}
          These four fields are extracted from the source text by rule, so the model’s answer can
          be checked against something other than itself. A disagreement does not mean the model
          is wrong — on the first run four of six were bugs in the extraction.
          {validation.reviewed > 0 && ` ${validation.reviewed} audience placements were made by review, in data/corrections.json, and are counted as agreement.`}
        </p>

        {validation.disagreements.length > 0 && (
          <Panel title="Open disagreements">
            {validation.disagreements.map((d) => (
              <Row key={`${d.no}-${d.field}`}
                   label={`${d.no} · ${FIELD_LABEL[d.field] ?? d.field}`}
                   value="" note={`derived ${d.derived} · model ${d.model}`} />
            ))}
          </Panel>
        )}

        <Panel title="Known gaps">
          <Row label="Referenced but not held, inside the listing's own range"
               value={String(missing.in_range.length)}
               note={missing.in_range.length
                 ? `${missing.in_range.join(", ")} — the IRD listing omits ${missing.in_range.length === 1 ? "it" : "them"} and no archive snapshot exists`
                 : "none"} />
          <Row label="Referenced but not held, published before the listing begins"
               value={String(missing.before_listing)}
               note="expected: the listing starts in 2006 and these are the older orders it amends" />
          <Row label="Documents needing OCR" value={String(h.needs_ocr.length)}
               note={h.needs_ocr.length
                 ? h.needs_ocr.map((d) => `${d.no} (${d.pages} page${d.pages === 1 ? "" : "s"})`).join(", ")
                 : "none"} />
          <Row label="Parse warnings" value={String(h.parse_warnings.length)}
               note={h.parse_warnings.map((w) => `${w.no}: ${w.warnings.join("; ")}`).join(" · ") || "none"} />
        </Panel>

        <Panel title="Summaries by the model's own confidence">
          {(["high", "medium", "low"] as const).map((k) =>
            h.confidence[k] === undefined ? null : (
              <Row key={k} label={`${k[0]!.toUpperCase()}${k.slice(1)} confidence`}
                   value={String(h.confidence[k])} />
            ))}
        </Panel>

        <Panel title="Pre-answered questions">
          <Row label="Rules with current published answers" value={`${answers.current}/${corpus.rules}`} />
          <Row label="Withdrawn — the rule changed since they were written" value={String(answers.stale)}
               note="a withdrawn set stays off the site until it is regenerated and read" />
          <Row label="Never written" value={String(answers.missing)} />
        </Panel>

        <p className="mt-6 text-[11.5px] leading-relaxed" style={{ color: "var(--faint)" }}>
          Built {formatDate(BUILT_AT)} from the corpus as it stood. The pipeline checks for new
          gazettes nightly and rebuilds this page whenever anything changes; the figures above come
          from{" "}
          <Link className="link" href="/">the same data the search uses</Link>, not from a separate
          record. The government’s own index of Extraordinary Gazettes is offline, so completeness
          here is a lower bound rather than a claim.
        </p>
      </article>
    </div>
  );
}
