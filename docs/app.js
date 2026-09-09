/* Vidhana — static search over the IRD gazette corpus.
 *
 * No framework, no build step. Everything the page shows comes from
 * docs/data/*.json, exported by `vidhana export-web` from the same resolver
 * output the CLI and the Atom feeds use — so the three surfaces cannot drift
 * into disagreeing about whether a rule is in force.
 *
 * Loading is two-stage on purpose. index.json (41 KB gzipped) blocks the first
 * render; bodies.json (223 KB gzipped) follows in the background. Until it
 * lands, search covers titles and summaries only, and the page says so rather
 * than silently returning fewer results.
 */
(() => {
  "use strict";

  const $ = (sel, root = document) => root.querySelector(sel);
  const el = (tag, attrs = {}, ...kids) => {
    const n = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") n.className = v;
      else if (k === "html") n.innerHTML = v;
      else if (k.startsWith("on")) n.addEventListener(k.slice(2), v);
      else n.setAttribute(k, v === true ? "" : String(v));
    }
    for (const kid of kids.flat()) {
      if (kid === null || kid === undefined || kid === false) continue;
      n.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    }
    return n;
  };
  const esc = (s) => String(s).replace(/[&<>"']/g,
    (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));

  // ── state ───────────────────────────────────────────────────────────────
  const S = {
    idx: null, bodies: null, bodiesPending: true,
    q: "", mode: "docs", subject: null, audience: null, status: null,
    asOf: null, open: null, detail: null, inverted: null
  };

  // ── data ────────────────────────────────────────────────────────────────
  async function boot() {
    try {
      S.idx = await (await fetch("data/index.json")).json();
    } catch (e) {
      $("#app").replaceChildren(el("div", { class: "empty" },
        el("b", {}, "Could not load the corpus"),
        "The search index failed to fetch. Reload, or use the Atom feeds."));
      return;
    }
    S.byNo = new Map(S.idx.gazettes.map((g) => [g.no, g]));
    S.threads = new Map((S.idx.threads || []).map((t) => [t.thread_id, t]));
    readUrl();
    render();
    // Background: the full text. Search upgrades from titles+summaries to the
    // whole corpus when it arrives; nothing blocks on it.
    fetch("data/bodies.json").then((r) => r.json()).then((b) => {
      S.bodies = b; S.bodiesPending = false; buildIndex(); render();
    }).catch(() => { S.bodiesPending = false; render(); });
  }

  // Ranking, standing and filtering live in core.js so they can be tested
  // against the CLI's behaviour without a browser. See docs/core.js.
  const { tokens, buildIndex: buildIdx, score: bm25 } = window.VidhanaCore;
  const standing = (g) => window.VidhanaCore.standing(g, S.asOf, fmt);
  function buildIndex() { S.inverted = buildIdx(S.idx.gazettes, S.bodies); }
  function score(no, qt) { return S.inverted ? bm25(S.inverted, no, qt) : 0; }

  // ── filtering ───────────────────────────────────────────────────────────
  function matches(g) {
    return window.VidhanaCore.matches(g, {
      subject: S.subject, audience: S.audience, status: S.status, asOf: S.asOf });
  }

  function results() {
    const qt = tokens(S.q);
    let rows = S.idx.gazettes.filter(matches);
    if (qt.length) {
      rows = rows.map((g) => ({ g, s: score(g.no, qt) })).filter((r) => r.s > 0)
                 .sort((a, b) => b.s - a.s || (a.g.published_date < b.g.published_date ? 1 : -1))
                 .map((r) => r.g);
    } else {
      rows = rows.slice().sort((a, b) => (a.published_date < b.published_date ? 1 : -1));
    }
    if (S.mode === "rules") {
      const seen = new Set(), out = [];
      for (const g of rows) {
        const key = g.thread_id ? "t" + g.thread_id : "g" + g.no;
        if (seen.has(key)) continue;
        seen.add(key);
        // A thread's answer is its current document, which may not be the row
        // that matched — that is the entire point of the mode.
        out.push(g.head_no && S.byNo.has(g.head_no) ? S.byNo.get(g.head_no) : g);
      }
      rows = out;
    }
    return rows;
  }

  const MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
  function fmt(iso) {
    if (!iso) return "";
    const [y, m, d] = iso.split("-");
    return `${Number(d)} ${MONTHS[Number(m) - 1]} ${y}`;
  }

  const warnIcon = () =>
    `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7
      3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>`;

  // ── URL state ───────────────────────────────────────────────────────────
  // Every view is addressable, so a result can be pasted into an email — which
  // is how a gazette reference actually travels between people.
  function readUrl() {
    const p = new URLSearchParams(location.search);
    S.q = p.get("q") || "";
    S.mode = p.get("mode") === "rules" ? "rules" : "docs";
    S.subject = p.get("subject"); S.audience = p.get("audience");
    S.status = p.get("status"); S.asOf = p.get("as_of");
    S.detail = p.get("no");
  }
  function writeUrl(push) {
    const p = new URLSearchParams();
    if (S.q) p.set("q", S.q);
    if (S.mode === "rules") p.set("mode", "rules");
    if (S.subject) p.set("subject", S.subject);
    if (S.audience) p.set("audience", S.audience);
    if (S.status) p.set("status", S.status);
    if (S.asOf) p.set("as_of", S.asOf);
    if (S.detail) p.set("no", S.detail);
    const url = location.pathname + (p.toString() ? "?" + p : "");
    if (push) history.pushState(null, "", url); else history.replaceState(null, "", url);
  }
  function go(patch, push = true) {
    Object.assign(S, patch);
    writeUrl(push);
    render();
  }
  addEventListener("popstate", () => { readUrl(); render(); });

  // ── chrome ──────────────────────────────────────────────────────────────
  const ICON_WARN = `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor"
    stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path
    d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path
    d="M12 9v4"/><path d="M12 17h.01"/></svg>`;

  function pill(st) {
    return el("span", { class: "pill " + st.cls },
      el("span", { class: "dot" }), st.pill);
  }

  function warnChip(g) {
    const n = (g.missing_refs || []).length || g.unresolved || 0;
    if (!n) return null;
    return el("span", { class: "chip warn", title:
      "A change made by a gazette we do not hold would not appear here." },
      el("span", { html: ICON_WARN }), `${n} gazette${n > 1 ? "s" : ""} missing from source`);
  }

  function facetButton(label, n, active, onclick, swatch) {
    return el("button", { class: "fac", "aria-pressed": active ? "true" : "false", onclick },
      swatch ? el("span", { class: "sw", style: `background:${swatch}` }) : el("span", { class: "sw" }),
      el("span", { class: "lbl" }, label),
      el("span", { class: "n" }, n));
  }

  function sidebar() {
    const gz = S.idx.gazettes;
    const count = (fn) => gz.filter(fn).length;
    const bySubject = new Map();
    for (const g of gz) bySubject.set(g.subject, (bySubject.get(g.subject) || 0) + 1);
    const byAud = new Map();
    for (const g of gz) for (const a of g.audience || []) byAud.set(a, (byAud.get(a) || 0) + 1);

    const groups = [
      ["Status", [
        ["Current documents", count((g) => g.status !== "rescinded" && (!g.head_no || g.head_no === g.no)),
         "current", "var(--ok)"],
        ["In force", count((g) => g.status !== "rescinded"), "inforce", "var(--ok)"],
        ["Rescinded", count((g) => g.status === "rescinded"), "rescinded", "var(--res)"]
      ].map(([l, n, id, sw]) =>
        facetButton(l, n, S.status === id, () => go({ status: S.status === id ? null : id }), sw))],
      ["Subject", [...bySubject.entries()].sort((a, b) => b[1] - a[1]).map(([s, n]) =>
        facetButton(s, n, S.subject === s, () => go({ subject: S.subject === s ? null : s })))],
      ["Who it affects", [...byAud.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8).map(([a, n]) =>
        facetButton(a, n, S.audience === a, () => go({ audience: S.audience === a ? null : a })))]
    ];

    return el("aside", { class: "side", id: "side" },
      el("a", { class: "brand", href: "?", onclick: (e) => { e.preventDefault(); go({ q: "", detail: null, subject: null, audience: null, status: null, asOf: null }); } },
        el("span", { html: `<svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><rect
          x="1.5" y="1.5" width="21" height="21" rx="5" fill="var(--accent)"/><path d="M7 8.5h10M7 12h10M7 15.5h6"
          stroke="var(--surface)" stroke-width="1.9" stroke-linecap="round"/></svg>` }),
        el("span", {}, el("b", {}, "Vidhana"), el("span", {}, "IRD gazettes, resolved"))),
      el("button", { class: "btn menu", onclick: () => $("#side").classList.toggle("open") }, "Filters"),
      el("div", { class: "facets" }, groups.map(([name, items]) =>
        el("div", { class: "fgroup" }, el("div", { class: "flabel" }, name), items))),
      el("div", { class: "sidefoot" },
        `${S.idx.counts.gazettes} gazettes · 2006–2026`, el("br"),
        `${S.idx.counts.recovered} recovered from the archive`));
  }

  function topbar() {
    const input = el("input", {
      id: "q", type: "search", value: S.q, placeholder: `Search ${S.idx.counts.gazettes} gazettes, full text`,
      "aria-label": "Search gazettes"
    });
    let t;
    input.addEventListener("input", () => {
      clearTimeout(t);
      t = setTimeout(() => go({ q: input.value, detail: null }, false), 140);
    });
    return el("div", { class: "topbar" },
      el("div", { class: "searchwrap" },
        el("span", { html: `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--dim)"
          stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path
          d="m20 20-3.5-3.5"/></svg>` }),
        input),
      el("div", { class: "seg", role: "group", "aria-label": "Result grouping" },
        el("button", { "aria-pressed": S.mode === "docs" ? "true" : "false",
          onclick: () => go({ mode: "docs" }) }, "Documents"),
        el("button", { "aria-pressed": S.mode === "rules" ? "true" : "false",
          onclick: () => go({ mode: "rules" }) }, "Rules")),
      el("button", { class: "btn", "aria-pressed": S.asOf ? "true" : "false",
        onclick: () => go({ asOf: S.asOf ? null : "2015-01-01" }) },
        el("span", { html: `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor"
          stroke-width="2" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path
          d="M12 7v5l3 2"/></svg>` }),
        S.asOf ? `As of ${fmt(S.asOf)}` : "As of today"));
  }

  function asOfBar() {
    if (!S.asOf) return null;
    const d = el("input", { type: "date", value: S.asOf, "aria-label": "As-of date" });
    d.addEventListener("change", () => go({ asOf: d.value || null }));
    return el("div", { class: "asofbar" },
      el("strong", { style: "font-size:12.5px;color:var(--accent)" }, "Showing the rule as it stood on"),
      d,
      el("span", { style: "font-size:12px;color:var(--dim)" },
        "tested on the effective date, not publication"),
      el("button", { class: "btn", onclick: () => go({ asOf: null }) }, "Clear"));
  }

  // ── result list ─────────────────────────────────────────────────────────
  function card(g) {
    const st = standing(g);
    const thread = g.thread_id ? S.threads.get(g.thread_id) : null;
    return el("button", { class: "card", onclick: () => go({ detail: g.no }) },
      el("div", { class: "idline" },
        el("span", { class: "no" }, g.no),
        g.source !== "ird-listing" ? el("span", { class: "chip",
          title: "Not in the IRD listing; recovered from the Internet Archive" }, "recovered") : null,
        el("span", { style: "flex-grow:1" }),
        pill(st)),
      el("h3", {}, g.title),
      st.conseq ? el("div", { class: "conseq", style: `color:var(--${st.cls})` }, st.conseq) : null,
      g.summary ? el("p", { class: "sum" }, g.summary) : null,
      el("div", { class: "meta" },
        el("span", { class: "date" }, fmt(g.published_date)),
        el("span", { class: "chip" }, g.subject),
        thread && thread.size > 1 ? el("span", { class: "chip" }, `${thread.size} documents in rule`) : null,
        warnChip(g),
        g.confidence && g.confidence !== "high"
          ? el("span", { class: "chip" }, `AI summary · ${g.confidence} confidence`) : null));
  }

  function listView() {
    const rows = results();
    const kids = [];
    kids.push(el("div", { style: "display:flex;align-items:baseline;gap:10px;margin-bottom:14px;flex-wrap:wrap" },
      el("span", { style: "font-size:13px;color:var(--dim)" },
        `${rows.length} ${S.mode === "rules" ? "rule" : "document"}${rows.length === 1 ? "" : "s"}`),
      S.mode === "rules" ? el("span", { class: "chip", style: "background:var(--accent-soft);color:var(--accent);border-color:transparent" },
        "one result per rule, answered by its current document") : null,
      S.bodiesPending && S.q ? el("span", { class: "chip" }, "searching titles and summaries — full text still loading") : null));

    if (!rows.length) {
      kids.push(el("div", { class: "empty" },
        el("b", {}, S.q ? `Nothing matches “${S.q}”` : "Nothing matches these filters"),
        S.bodiesPending ? "Full text is still loading — try again in a moment."
                        : "Full text of every gazette is searched, not just titles."));
    } else {
      kids.push(el("div", { class: "results" }, rows.slice(0, 60).map(card)));
      if (rows.length > 60) kids.push(el("p", { class: "note", style: "margin-top:14px" },
        `Showing the 60 best matches of ${rows.length}. Narrow with the filters on the left.`));
    }
    kids.push(el("p", { class: "note", style: "margin-top:22px" },
      "Summaries are machine-written; the gazette is the source of truth. “In force” means ",
      el("em", {}, "not rescinded by another gazette in this corpus"),
      " — weaker than a legal determination. Not legal advice."));
    return el("div", { class: "content" }, kids);
  }

  // ── detail ──────────────────────────────────────────────────────────────
  function detailView(no) {
    const g = S.byNo.get(no);
    if (!g) return el("div", { class: "content" }, el("div", { class: "empty" },
      el("b", {}, `No gazette ${no}`), "It may be referenced by a document we hold but missing from the corpus."));

    const thread = g.thread_id ? S.threads.get(g.thread_id) : null;
    const head = thread && S.byNo.get(thread.head_no);
    const answer = head || g;
    const st = standing(answer);
    const members = thread
      ? S.idx.gazettes.filter((x) => x.thread_id === g.thread_id)
          .sort((a, b) => (a.published_date < b.published_date ? -1 : 1))
      : [g];

    // Referenced but not held — the reason "in force" is conditional.
    const missing = new Set();
    for (const m of members) for (const r of m.missing_refs || []) missing.add(r);

    const events = [];
    for (const m of members) {
      events.push({ no: m.no, date: m.published_date, g: m,
                    kind: m.no === answer.no ? "ok" : "sup" });
    }
    for (const mm of missing) events.push({ no: mm, date: null, kind: "missing" });
    events.sort((a, b) => (a.date || "0000") < (b.date || "0000") ? -1 : 1);

    return el("div", { class: "content", style: "max-width:1000px;margin:0 auto" },
      el("button", { class: "btn", style: "margin-bottom:16px",
        onclick: () => go({ detail: null }) }, "← Back to results"),

      el("div", { style: "display:flex;gap:9px;align-items:center;flex-wrap:wrap;margin-bottom:13px" },
        el("span", { class: "chip" }, g.subject),
        thread ? el("span", { class: "chip" }, `${thread.size} documents`) : el("span", { class: "chip" }, "standalone"),
        thread ? el("span", { class: "chip" }, `${thread.first_date.slice(0, 4)} – ${thread.last_date.slice(0, 4)}`) : null,
        missing.size ? el("span", { class: "chip warn" },
          el("span", { html: ICON_WARN }), `${missing.size} gazette${missing.size > 1 ? "s" : ""} missing from source`) : null),

      el("div", { class: "answer " + st.cls },
        el("div", { style: "display:flex;align-items:center;gap:10px;flex-wrap:wrap" },
          pill(st), el("span", { style: "flex-grow:1" }),
          el("span", { class: "date" }, `effective ${fmt(answer.effective_from)}`)),
        el("h1", {}, el("span", { class: "mono" }, answer.no), " — ", answer.title),
        answer.summary ? el("p", { style: "margin:9px 0 0;font-size:14.5px;line-height:1.55;color:var(--dim);max-width:700px" },
          answer.summary) : null,
        answer.confidence && answer.confidence !== "high"
          ? el("p", { class: "note", style: "margin-top:8px" },
              `This summary was generated with ${answer.confidence} confidence. Read the gazette before relying on it.`)
          : null,
        el("div", { style: "margin-top:15px;display:flex;gap:10px;flex-wrap:wrap" },
          el("a", { class: "primary", href: answer.source_url, target: "_blank", rel: "noopener" },
            "Open the gazette PDF →"),
          answer.no !== g.no ? el("a", { class: "ghost", href: "?no=" + encodeURIComponent(g.no),
            onclick: (e) => { e.preventDefault(); go({ detail: g.no }); } }, `You searched ${g.no}`) : null)),

      missing.size ? el("div", { class: "gapnote" },
        el("span", { html: ICON_WARN.replace(/width="11" height="11"/, 'width="16" height="16"') }),
        el("span", {}, el("strong", {}, "This rule’s history is incomplete. "),
          `${[...missing].join(", ")} ${missing.size > 1 ? "are" : "is"} referenced by a document we hold but missing from the IRD listing, so a change made by a gazette we do not hold would not appear below.`)) : null,

      el("div", { class: "kicker", style: "margin:30px 0 12px" }, "How it got here"),
      el("div", { class: "timeline" }, events.map((e, i) => timelineRow(e, i, events.length))),

      el("div", { class: "grid2", style: "margin-top:14px" },
        el("div", { class: "panel" },
          el("div", { class: "kicker" }, "Who this affects"),
          el("div", { style: "margin-top:10px;display:flex;gap:7px;flex-wrap:wrap" },
            (answer.audience || []).length
              ? answer.audience.map((a) => el("span", { class: "chip" }, a))
              : el("span", { class: "chip" }, "not stated")),
          el("p", { class: "note", style: "margin-top:10px" },
            "Inferred from the enabling Act — gazettes rarely state who they bind, and the model may only narrow within the Act’s known audiences.")),
        el("div", { class: "panel" },
          el("div", { class: "kicker" }, "Enabling Act"),
          el("div", { style: "margin-top:10px;font-size:14px;font-weight:500" },
            answer.enabling_act || "not parsed"),
          answer.source !== "ird-listing" ? el("p", { class: "note", style: "margin-top:10px" },
            "Recovered from the Internet Archive — this gazette is not in the IRD listing.") : null)),

      el("p", { class: "note", style: "margin-top:22px" },
        "Summaries are machine-written; the gazette is the source of truth. Not legal advice."));
  }

  function timelineRow(e, i, n) {
    const isMissing = e.kind === "missing";
    const g = e.g;
    const st = g ? standing(g) : null;
    const node = el("span", { class: "spine-node node " + (isMissing ? "missing" : ""),
      style: isMissing ? "" : `background:var(--${e.kind === "ok" ? "ok" : "dim"})` });
    node.className = "node" + (isMissing ? " missing" : "");
    if (!isMissing) node.style.background = e.kind === "ok" ? "var(--ok)" : "var(--dim)";
    if (e.kind === "ok") node.style.boxShadow = "0 0 0 3px var(--surface), 0 0 0 5px var(--ok)";

    const body = el("div", { class: "evbody" },
      el("div", { style: "display:flex;align-items:center;gap:10px;flex-wrap:wrap" },
        el("span", { class: "mono", style: "font-size:13.5px;font-weight:" + (e.kind === "ok" ? 600 : 500) }, e.no),
        e.date ? el("span", { class: "date" }, fmt(e.date)) : null,
        isMissing ? el("span", { class: "chip warn" }, "not held")
                  : el("span", { class: "pill " + st.cls }, el("span", { class: "dot" }), st.pill)),
      isMissing
        ? el("p", { style: "margin:4px 0 0;font-size:13.5px;color:var(--dim)" },
            "Referenced by a document we hold, but absent from the IRD listing.")
        : el("p", { style: "margin:4px 0 0;font-size:13.5px;color:var(--dim)" }, g.title));

    const row = el("div", { class: "ev", style: isMissing ? "" : "cursor:pointer" });
    if (!isMissing) {
      row.addEventListener("click", () => go({ detail: e.no }));
      row.setAttribute("role", "button");
      row.setAttribute("tabindex", "0");
    }
    row.append(el("div", { class: "spine" },
      el("span", { class: "up", style: i === 0 ? "background:transparent" : "" }),
      node,
      el("span", { class: "dn", style: i === n - 1 ? "background:transparent" : "" })), body);
    return row;
  }

  // ── hero (no query, no filters) ─────────────────────────────────────────
  function hero() {
    const jobs = [
      ["1", "What is the rule right now?", "Search, then switch to Rules. One result per rule, answered by the document that is current today.",
       { mode: "rules", q: "tax invoice" }],
      ["2", "What applied back in 2015?", "Set an as-of date. Effective dates are often retroactive, so this differs from filtering by publication.",
       { q: "transfer pricing", asOf: "2015-01-01" }],
      ["3", "Does this affect me?", "Filter by audience — notaries, employers, VAT-registered businesses — inferred from the enabling Act.",
       { audience: "notaries" }]
    ];
    return el("div", { class: "hero" },
      el("h1", {}, "What the rule", el("br"), "actually is. Now."),
      el("p", {}, "Half of these gazettes amend or rescind another one, so the current state of a rule frequently exists in no single document. Search returns the rule — not the documents that mention it."),
      el("div", { class: "jobs" }, jobs.map(([n, q, how, patch]) =>
        el("a", { class: "job", href: "#", onclick: (e) => { e.preventDefault(); go(patch); } },
          el("span", { class: "n" }, n), el("b", {}, q), el("span", {}, how)))),
      el("div", { class: "panel", style: "margin-top:30px" },
        el("div", { style: "font-size:13px;font-weight:600" }, "What this cannot tell you"),
        el("p", { class: "note", style: "margin-top:7px" },
          `The IRD listing omits gazettes from inside its own date range — ${S.idx.counts.recovered} were recovered from the Internet Archive and are marked as such. A gazette nobody indexes, which rescinds one we hold, would be invisible here. Where a rule’s history has a hole, results say so. Summaries are machine-written; the gazette is the source of truth. Not legal advice.`)));
  }

  // ── render ──────────────────────────────────────────────────────────────
  function render() {
    const bare = !S.q && !S.subject && !S.audience && !S.status && !S.asOf && !S.detail;
    const main = el("div", { class: "main" }, topbar(), asOfBar(),
      S.detail ? detailView(S.detail) : bare ? hero() : listView());
    $("#app").replaceChildren(el("div", { class: "shell" }, sidebar(), main));
    document.title = S.detail ? `${S.detail} · Vidhana`
                   : S.q ? `${S.q} · Vidhana` : "Vidhana — what the rule actually is";
  }

  // The script tag sits at the end of <body>, so the DOM is already parsed —
  // but check readyState anyway rather than assume, since a deferred or
  // module-typed load would fire this after DOMContentLoaded has passed.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
