# The web front end

Search, in a browser, at
[gedara-workshop.github.io/vidhana](https://gedara-workshop.github.io/vidhana/).
**Next.js 15, App Router, TypeScript**, statically exported and deployed from
GitHub Actions.

```bash
python3 -m vidhana export-web    # writes docs/data/{index,bodies}.json
cd web && npm run dev            # the app
cd web && npm test               # 12 unit tests
```

## Why a framework, when a single page worked

The first version was 550 lines of vanilla JavaScript, and it worked. It was
also **one page with query parameters**, which means a crawler saw nothing.

The Next build pre-renders **144 gazette pages and 20 rule pages**. That is the
whole argument, and it is a product one rather than a technical one: search is
the acquisition channel for a tool nobody has heard of. Someone looking for a
tax invoice format should land on `2481/22`, read *"Superseded. 2500/106 is the
current document in this rule"* in the search snippet, and follow it — never
having known this site existed. No amount of polish on a single-page app gets
that, because there is nothing for a crawler to read.

`output: "export"` is a deployment choice, not an architectural one. Every route
uses server components and `generateStaticParams`, so moving to a Node host for
ISR or route handlers means editing `next.config.ts` rather than the
application.

## Why the browser gets the whole corpus

| file | raw | gzipped | when |
|---|---:|---:|---|
| `index.json` | 209 KB | **41 KB** | blocking, first render |
| `bodies.json` | 1077 KB | **223 KB** | background |

That second number decided the architecture. 1.1 MB of statutory text gzips to
223 KB, so the browser can hold the *real* corpus and run the same search the
CLI runs — rather than a cut-down preview that quietly answers a different
question from the tool it claims to mirror.

Until `bodies.json` lands, search covers titles and summaries, and the page
**says so**. Silently returning fewer results would be the worse failure.

## What the two surfaces must share, and what they need not

`docs/core.js` holds everything that has to agree with `vidhana/search.py`, kept
free of any DOM reference so it can be tested through `node` without a browser.

**They must agree on which documents match.** A document the CLI finds and the
browser does not is a document a reader concludes does not exist.

**They must agree on standing.** Ranking is a convenience; standing is the
claim someone acts on. `standing()` reads the resolver's output — it never
recomputes state from the reference graph in JavaScript.

**They need not agree on ranking.** fts5 stems with porter; this stems with a
light plural fold, and the two bm25 implementations normalise length
differently. Measured over all 144 documents they agree on 4–5 of the top 5 and
order them differently for about half of queries. Exact parity is not worth
chasing, and the test asserts the two properties above rather than pretending
otherwise — an earlier version asserted equal top results, passed on a
four-document fixture, and would have failed on the real corpus.

## Three things the browser got wrong first

**Terms were ORed.** `gazette_fts MATCH 'tax invoice'` requires both words.
Scoring them as OR turned a 13-document answer into 60, because every gazette
in a tax corpus contains "tax". Ranking does not rescue that: the right
documents still come first, but the reader is handed a page of noise with no
signal that their query was read loosely.

**As-of reported today's standing.** Searching transfer pricing as of 1 January
2015 correctly returned `1823/05` — and labelled it **Rescinded**, which is
true now and was false then. It contradicted the whole feature. With an as-of
date, standing reads *In force on this date*, and what the document became
since is the second line rather than the headline.

**Nothing called `boot()`.** The app rendered its own no-JavaScript fallback and
looked plausible while doing it. Caught by driving a real browser; no amount of
reading would have found it, because every file parsed cleanly.

## The qualifier system

A result can carry five caveats. Stacked as badges they are a wall nobody
reads, and the one that matters most is lost in it. Two moves:

**State before sentence.** The legal state is a pill you recognise at a glance;
only the *consequence* gets words. `In force · current` carries no consequence
line at all, because there is nothing to act on.

**Each caveat attaches to the claim it weakens.**

| caveat | where | why there |
|---|---|---|
| provenance (`recovered`) | beside the number | qualifies the document's identity |
| state | pill, always present | the only thing a reader must act on |
| consequence | one line under the title | the only sentence |
| missing history | chip row | weakens the standing claim, so it sits with the facts |
| summary confidence | chip row | scoped so it can never read as doubt about the law |

Rescinded uses a muted brick, not alarm red: a rescinded gazette is a normal
historical fact, and shouting makes the genuinely urgent case unreadable. Every
state carries a word as well as a colour.

## Addressability

Every view is a URL — `?q=&mode=rules&subject=&audience=&status=&as_of=&no=` —
with real history entries, so back works and a result can be pasted into an
email. That is how a gazette reference actually travels between people, and a
search tool that cannot be linked to loses the argument before it starts.

## Layout

```
web/lib/        types, search, standing — the parts that must agree with Python
web/app/        routes: search, /gazette/[slug], /rule/[id], /feeds
web/components/ the qualifier system, made real
docs/data/      the exported corpus (written by Python, committed)
docs/feeds/     the Atom feeds (written by Python, copied into the build)
design/         .dc.html sources behind the design canvas
```

Two workflows, deliberately separate. `gazettes.yml` owns the corpus and must
not miss a night; `pages.yml` owns the site and runs after it. A failed site
build never blocks the gazette check.

## Known limits

- **Ranking differs slightly from the CLI**, as above.
- **No pagination.** The list caps at the 60 best matches and says so; with 144
  documents and facets, scrolling further has not yet been worth building.
- **Search needs JavaScript.** The fallback points at the Atom feeds, which
  carry the same resolved state and need none of it.
- **`docs/data` is committed**, so the repo carries ~1.3 MB of derived JSON. It
  is the same trade as the feeds: a derived artefact that must not change
  spuriously belongs in version control, and the exporter writes it byte-stably
  so an unchanged rebuild produces an empty diff.
