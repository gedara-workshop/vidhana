import Link from "next/link";

import { toSlug } from "@/lib/standing";
import type { RuleQuestion } from "@/lib/types";

/* Pre-answered questions for a rule.
 *
 * Server-rendered, so every question and answer is in the page's HTML — that is
 * half the point: these are the sentences people type into a search engine.
 * The disclosure is not optional furniture. The answers were written by a
 * model, and the page must say so, say how they were checked, and say that the
 * gazettes remain the source of truth, in the same breath as the answers. */

export function RuleQuestions({ questions }: { questions: RuleQuestion[] }) {
  if (questions.length === 0) return null;
  return (
    <section className="mt-6" aria-labelledby="rule-questions">
      <p id="rule-questions" className="sec mb-2">Questions about this rule</p>
      <div className="overflow-hidden rounded-[8px] border" style={{ borderColor: "var(--line)" }}>
        {questions.map((qa) => (
          <div key={qa.question} className="border-b px-4 py-3 last:border-0"
               style={{ borderColor: "var(--line-soft)" }}>
            <h3 className="text-[13.5px] font-semibold leading-snug">{qa.question}</h3>
            <p className="mt-1 text-[13px] leading-relaxed" style={{ color: "var(--dim)" }}>
              {qa.answer}
            </p>
            <p className="mt-2 flex flex-wrap items-center gap-1">
              <span className="mono text-[10.5px]" style={{ color: "var(--faint)" }}>from</span>
              {qa.cites.map((c) => (
                <Link key={c} className="tag mono" href={`/gazette/${toSlug(c)}/`}>{c}</Link>
              ))}
            </p>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11.5px] leading-relaxed" style={{ color: "var(--faint)" }}>
        Written by an AI model from the gazettes in this rule, then checked against them: every
        gazette, date and amount an answer states appears in those documents. The answers are
        withdrawn automatically when the rule changes. Not legal advice — the gazette PDFs are the
        source of truth.
      </p>
    </section>
  );
}

/** schema.org FAQPage for the same questions, so a search engine reads them as
 *  questions and answers rather than as page text. `<` is escaped because this
 *  is written into a <script> element, and an answer containing "</script>"
 *  would otherwise end it. */
export function RuleQuestionsJsonLd({ questions }: { questions: RuleQuestion[] }) {
  if (questions.length === 0) return null;
  const data = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: questions.map((qa) => ({
      "@type": "Question",
      name: qa.question,
      acceptedAnswer: { "@type": "Answer", text: qa.answer },
    })),
  };
  return (
    <script type="application/ld+json"
            dangerouslySetInnerHTML={{ __html: JSON.stringify(data).replace(/</g, "\\u003c") }} />
  );
}
