# Phase 4 — Alerts

A daily check that says what is new and, more usefully, what it *changes*.
Delivered as Atom feeds, published from the repository, updated by a scheduled
GitHub Action. No server, no subscriber list, no personal data.

**Status: complete.**

```bash
python3 -m vidhana whatsnew --since 2025-01-01 [--subject vat] [--kind rescinds]
python3 -m vidhana feed                        # write docs/feeds/*.xml
python3 -m vidhana summaries export|import     # the LLM output, tracked in git
```

## Why RSS and not email

At **3–6 gazettes a year**, an email pipeline is mostly unused plumbing:
subscriber list, sending provider, unsubscribe handling, deliverability, and a
hosting decision forced early. A feed is a static file. It holds no personal
data, it needs no server, and it composes — anyone can pipe it into email,
Slack or IFTTT later without this project building any of that.

Feeds live under `docs/` so GitHub Pages serves them straight from the repo,
which is what keeps the hosting question genuinely open rather than answered by
accident.

## Events are derived, not accumulated

"2500/106 amends 2481/22" is a fact about the data — true whenever it is asked,
not an occurrence that has to be caught as it happens. So `derive` recomputes
every event from the corpus on each run. This makes the whole phase forgiving:

- a missed cron run loses nothing;
- a rebuilt database produces the same events as the one it replaced;
- running the pipeline twice does not double-notify anyone.

The single thing that cannot be re-derived is *when we first saw an event*, and
that is all `gazette_event` stores. Without it every entry would take a fresh
timestamp on every run, and a reader's client would re-notify them about a
gazette from 2014 every night — a bug that would look like the feed working.

Events that stop being derivable are deleted. A reference can be re-parsed away
by a fix to `parse.py`, and the feed should say what the corpus says now rather
than carry an entry no evidence supports.

## What counts as news

| kind | count | meaning |
|---|---:|---|
| `published` | 137 | a gazette exists |
| `amends` | 47 | it changes another gazette |
| `rescinds` | 17 | it revokes another gazette |
| `effective_change` | 1 | it moves *when* another gazette bites |

A new gazette appearing is the obvious event and the least useful one alone. A
reader does not want to be told a document exists; they want to be told that
something they already follow has changed under them. So a relation event names
both gazettes and the entry can say what the rule's current document now is.

**`cites` is excluded.** It points at an unrelated instrument — a
depreciation-rates gazette cited in passing — and changes nothing's standing.

**Dangling edges are excluded.** 13 references point at gazettes the IRD listing
does not carry, and for those we can say neither what changed nor what the rule
now is. An alert that can say neither is noise wearing an alert's clothes.

**`effective_change` is the rarest kind and the most valuable.** `2500/106` moved
the tax invoice format from July to October 2026. A reader who acted on
`2481/22` alone would have been three months early — precisely the failure this
project exists to prevent — so it gets its own kind rather than being folded
into `amends`.

## One entry per gazette, not per event

`2500/106` raises three events: it is new, it amends `2481/22`, and it moves that
gazette's effective date. Those are three facts about one document, and a feed
reader would show them as three notifications with near-identical text. The feed
groups them; `whatsnew` keeps them separate, because there the granularity is
the point.

Titles are built as clauses rather than a list of labels. The label form produced

```
2481/22 rescinded and new gazette 2463/05
```

which reads as though `2463/05` were the new one — the opposite of what
happened. It now reads:

```
2500/106 [vat] amends 2481/22 and changes when it takes effect
2481/22  [vat] rescinds 2463/05
2463/05  [vat] new: The format and specification of the Tax Invoice…
```

Two further decisions:

- **The feed's `updated` is the newest event's date, not `now()`.** A nightly run
  that finds nothing must not restamp the feed; clients read that as activity,
  and a quiet corpus should look quiet.
- **A medium- or low-confidence summary says so in the entry.** It reaches the
  reader looking exactly as authoritative as a high-confidence one otherwise.

## The nightly job

`.github/workflows/gazettes.yml`, 02:17 UTC daily. State lives in the repository
rather than in the runner:

| tracked | why |
|---|---|
| `data/listing/gazette-listing.json` | the index |
| `data/manifest.csv` | every PDF fetched, with sha256 |
| `data/summaries.json` | the LLM output — the only artefact that costs money |
| `docs/feeds/*.xml` | the published feeds |

The database is gitignored and rebuilt each run. The PDFs are cached because
they are bulky and re-fetchable, not because they are precious: a cache miss
costs time and politeness, never correctness or money.

`summaries import` runs **before** `structure`, so only genuinely new gazettes
reach the model. Without that, a cold runner would re-summarise all 137
documents — $0.16 and 137 API calls to reproduce something already held.

The commit step stages only those four paths and exits cleanly when none moved,
so a quiet month produces no commits at all. That keeps the history a record of
the law changing rather than of the workflow running.

## Reproducibility, verified

A database built from nothing with `OPENAI_API_KEY` unset — `init`, `sync`,
`fetch --reparse`, `summaries import`, `resolve`, `reindex`, `feed` — grades
identically on all four validation fields and produces **byte-identical feeds**.

Cloning the repo and fetching the PDFs now yields the whole corpus with no API
key at all.

## Known limits

- **"In force" still means "not rescinded by another gazette we hold."** 13 of
  106 graph edges dangle, so a rescission we cannot see would not raise an
  event. This is the same limit the resolver carries, surfaced to more people.
- **The feed cannot say what a rule *reads* like after four amendments.** It
  says which document is current. Consolidating amended text remains unsolved.
- **No per-audience feeds.** Subject is deterministic and splits cleanly;
  audience is grounded but multi-valued, and a reader wanting "everything
  affecting notaries" would get a feed whose membership shifts as summaries are
  re-run. Subject feeds are stable, so v0 ships those.
- **Nobody is subscribed.** The feed is correct and published; whether anyone
  wants it is the next thing to find out, and no amount of building answers it.
