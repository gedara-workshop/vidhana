/* What the corpus is, in one place.
 *
 * The site said "144 gazettes · 2006–2026" and "Sri Lanka's government
 * gazettes", which reads as all of them. It is one department's tax
 * gazettes: a gazette number is <weekly issue>/<n-th Extraordinary of that
 * week>, so week 2500 alone published at least 106 Extraordinary gazettes and
 * this corpus holds one of them. Across the 95 weeks it touches at all, at
 * least 2,115 exist.
 *
 * The holes it can see are already disclosed per rule and per feed entry. This
 * is the one it cannot see from inside: a reader acting on the *absence* of a
 * document that was never in scope. Narrow is the design — deep beats broad
 * while one person maintains it — but it has to be stated, not implied.
 */

export const SCOPE_SHORT = "IRD tax & VAT gazettes";

export function ScopeNote({ className = "" }: { className?: string }) {
  return (
    <p className={`text-[11.5px] leading-relaxed ${className}`} style={{ color: "var(--faint)" }}>
      <strong style={{ color: "var(--dim)" }}>Scope.</strong>{" "}
      Inland Revenue tax and VAT gazettes only — the department’s own published list, plus
      gazettes missing from it that were recovered from the Internet Archive. Customs, labour,
      imports and every other ministry are out of scope, and some tax changes are made by
      amending an Act rather than by gazette, so they never appear as a gazette at all.
    </p>
  );
}
