/* Vidhana search core — the parts that must agree with vidhana/search.py.
 *
 * Kept separate from app.js and free of any DOM reference so it can be
 * exercised by tests. If the browser and the CLI ever rank differently, or
 * disagree about whether a rule is in force, this is the file at fault.
 */
(function (root) {
  "use strict";

  // Mirrors search._depluralise: fold only the final token of a term, since
  // that is where the head noun sits. `debits-tax` must not become `debit-tax`.
  function depl(w) {
    if (w.length < 4 || w.endsWith("ss")) return w;
    if (w.endsWith("ies")) return w.slice(0, -3) + "y";
    if (/(ses|xes|ches|shes)$/.test(w)) return w.slice(0, -2);
    return w.endsWith("s") ? w.slice(0, -1) : w;
  }

  const STOP = new Set(["the", "of", "and", "to", "in", "a", "for", "on", "by", "no"]);

  function tokens(s) {
    const m = String(s || "").toLowerCase().match(/[a-z0-9][a-z0-9/-]*/g);
    if (!m) return [];
    return m.map(depl).filter((t) => t.length > 1 && !STOP.has(t));
  }

  // Field weights mirror search.WEIGHTS (title 6, summary 4, body 1), over the
  // same three fields gazette_fts indexes. Tags and audience are deliberately
  // NOT folded in here even though they are available: the CLI does not index
  // them, and a field the two surfaces do not share is a guaranteed
  // disagreement. They stay filterable through the facets, which is the better
  // affordance for them anyway.
  const FIELD_W = { title: 6, summary: 4, body: 1 };

  function buildIndex(gazettes, bodies) {
    const df = new Map(), docs = new Map();
    const avg = { title: 0, summary: 0, body: 0 };
    for (const g of gazettes) {
      const fields = {
        title: tokens(g.title),
        summary: tokens(g.summary),
        body: tokens(bodies ? bodies[g.no] : "")
      };
      const tf = {}, seen = new Set();
      for (const f of Object.keys(FIELD_W)) {
        const m = new Map();
        for (const t of fields[f]) m.set(t, (m.get(t) || 0) + 1);
        tf[f] = m;
        for (const t of m.keys()) seen.add(t);
        avg[f] += fields[f].length;
      }
      for (const t of seen) df.set(t, (df.get(t) || 0) + 1);
      docs.set(g.no, { tf, len: { title: fields.title.length, summary: fields.summary.length,
                                  body: fields.body.length } });
    }
    for (const f of Object.keys(avg)) avg[f] = avg[f] / (docs.size || 1) || 1;
    return { df, docs, avg, n: docs.size };
  }

  function has(d, t) {
    return d.tf.title.has(t) || d.tf.summary.has(t) || d.tf.body.has(t);
  }

  // BM25 per field, summed with the field weights — the shape SQLite's bm25()
  // uses with per-column weights, so the two rank alike on the same corpus.
  //
  // Terms are ANDed, not ORed. `gazette_fts MATCH 'tax invoice'` requires both
  // words, and matching either instead turns a three-document answer into
  // sixty: every gazette in a tax corpus contains "tax". Scoring alone does not
  // save it — the right documents rank first, but the reader is handed a page
  // of noise and no signal that the query was understood loosely.
  function score(index, no, queryTokens) {
    const d = index.docs.get(no);
    if (!d) return 0;
    for (const t of queryTokens) if (!has(d, t)) return 0;
    const k1 = 1.2, b = 0.75;
    let total = 0;
    for (const t of queryTokens) {
      const nq = index.df.get(t) || 0;
      if (!nq) continue;
      const idf = Math.log(1 + (index.n - nq + 0.5) / (nq + 0.5));
      for (const f of Object.keys(FIELD_W)) {
        const freq = d.tf[f].get(t) || 0;
        if (!freq) continue;
        total += FIELD_W[f] * idf *
          (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * d.len[f] / index.avg[f]));
      }
    }
    return total;
  }

  // Standing, derived exactly as search._annotate does. Never recomputed from
  // the reference graph in the browser: the resolver already decided.
  //
  // `asOf` changes the question being answered, and therefore the answer. A
  // document that is rescinded today may have been the rule on the date asked
  // about — 1823/05 is rescinded now and was transfer pricing law on 1 January
  // 2015 — so labelling it "Rescinded" while time-travelling contradicts the
  // whole feature. Callers that pass an as-of date have already filtered on it,
  // so reaching here means the document was operative then; what it became
  // since is the useful second line, not the headline.
  function standing(g, asOf, fmtDate) {
    const d = fmtDate || ((x) => x);
    if (asOf) {
      const since = g.rescinded_by
        ? "Rescinded since, by " + g.rescinded_by +
          (g.rescinded_from ? " from " + d(g.rescinded_from) : "")
        : (g.head_no && g.head_no !== g.no)
          ? "Superseded since — " + g.head_no + " is the current document"
          : null;
      return { cls: "ok", pill: "In force on this date", conseq: since };
    }
    if (g.status === "rescinded") {
      return { cls: "res", pill: "Rescinded",
               conseq: g.rescinded_by
                 ? "Rescinded by " + g.rescinded_by +
                   (g.rescinded_from ? ", from " + d(g.rescinded_from) : "")
                 : null };
    }
    if (g.head_no && g.head_no !== g.no) {
      return { cls: "sup", pill: "Superseded",
               conseq: g.head_no + " is the current document in this rule" };
    }
    return { cls: "ok", pill: "In force · current", conseq: null };
  }

  // Mirrors search._filters. `as_of` tests the effective date, never
  // publication: 2316/13 was published in January 2023 and took effect in
  // October 2022, so publication order is not chronological order.
  function matches(g, f) {
    if (f.subject && g.subject !== f.subject) return false;
    if (f.audience && !(g.audience || []).includes(f.audience)) return false;
    if (f.status === "current" && !(g.status !== "rescinded" && (!g.head_no || g.head_no === g.no))) return false;
    if (f.status === "inforce" && g.status === "rescinded") return false;
    if (f.status === "rescinded" && g.status !== "rescinded") return false;
    if (f.asOf) {
      if (!g.effective_from || g.effective_from > f.asOf) return false;
      if (g.rescinded_from && g.rescinded_from <= f.asOf) return false;
    }
    return true;
  }

  root.VidhanaCore = { depl, tokens, buildIndex, score, standing, matches, FIELD_W };
})(typeof window !== "undefined" ? window : globalThis);
