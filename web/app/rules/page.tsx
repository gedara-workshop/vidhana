import type { Metadata } from "next";
import Link from "next/link";

import { allThreads, gazetteMap, threadMembers } from "@/lib/corpus";
import { rulePath } from "@/lib/rules";
import { formatDate } from "@/lib/standing";

export const metadata: Metadata = {
  title: "Rules",
  description:
    "Every rule in the Sri Lankan IRD gazette corpus, with the document that is " +
    "currently in force and the history behind it.",
};

/** The index of rules. A rule is a set of gazettes that between them define one
 *  thing over time; the answer is usually in none of them individually, which
 *  is why this page exists separately from the list of documents. */
export default function RulesPage() {
  const threads = allThreads().sort((a, b) => (a.last_date < b.last_date ? 1 : -1));
  const byNo = gazetteMap();

  return (
    <div className="h-full overflow-y-auto">
      <div className="mx-auto max-w-5xl px-5 py-6">
        <h1 className="text-[20px] font-bold tracking-tight">Rules</h1>
        <p className="mt-1 max-w-[640px] text-[13px]" style={{ color: "var(--dim)" }}>
          {threads.length} rules across the corpus. Each is a set of gazettes that between them
          define one thing over time — the current state usually exists in none of them alone.
        </p>

        <div className="mt-5 overflow-hidden rounded-[8px] border" style={{ borderColor: "var(--line)" }}>
          <table className="w-full text-left">
            <thead>
              <tr className="sec" style={{ background: "var(--panel)" }}>
                <th className="px-3 py-2 font-semibold">Current document</th>
                <th className="hidden px-3 py-2 font-semibold sm:table-cell">Subject</th>
                <th className="px-3 py-2 text-right font-semibold">Docs</th>
                <th className="hidden px-3 py-2 text-right font-semibold md:table-cell">Span</th>
              </tr>
            </thead>
            <tbody>
              {threads.map((t) => {
                const head = byNo.get(t.head_no);
                const members = threadMembers(t.thread_id);
                const gaps = new Set(members.flatMap((m) => m.missing_refs)).size;
                return (
                  <tr key={t.thread_id} className="border-t hover:bg-[var(--raised)]"
                      style={{ borderColor: "var(--line-soft)" }}>
                    <td className="px-3 py-[9px]">
                      <Link href={rulePath(t)} className="block">
                        <span className="flex items-center gap-2">
                          <span className="mono text-[12px] font-semibold">{t.head_no}</span>
                          {gaps > 0 && <span className="tag tag-warn">gap</span>}
                        </span>
                        <span className="clamp-1 mt-[2px] block text-[12.5px]"
                              style={{ color: "var(--dim)" }}>
                          {head?.title ?? "—"}
                        </span>
                      </Link>
                    </td>
                    <td className="hidden px-3 py-[9px] sm:table-cell">
                      <span className="tag">{t.subject}</span>
                    </td>
                    <td className="mono px-3 py-[9px] text-right text-[12px]">{t.size}</td>
                    <td className="mono hidden px-3 py-[9px] text-right text-[11.5px] md:table-cell"
                        style={{ color: "var(--faint)" }}>
                      {t.first_date.slice(0, 4)}–{t.last_date.slice(0, 4)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        <p className="mt-4 text-[11.5px] leading-relaxed" style={{ color: "var(--faint)" }}>
          A “gap” marks a rule that references a gazette the corpus does not hold — the IRD
          listing omits documents from inside its own date range. Where a rule has one, a change
          made by a gazette we do not have would not appear.
          Last updated {formatDate(threads[0]?.last_date ?? null)}.
        </p>
      </div>
    </div>
  );
}
