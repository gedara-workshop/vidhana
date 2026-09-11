# Corpus completeness

Phase 0 left one question open: *is the IRD listing the whole story?* This is
the answer, and it is worse than expected in one way and better in another.

**Short version.** The listing is incomplete inside its own date range, the
official index that would let anyone verify it is offline, 7 of the 8 known
gaps have been recovered from the Internet Archive, and the residual
uncertainty is now disclosed in search and in the feed rather than documented
here and forgotten.

```bash
python3 -m vidhana verify [--find]   # what is missing, and is it recoverable
python3 -m vidhana backfill          # recover it, and record it in data/recovered.json
python3 -m vidhana restore           # re-acquire every recorded recovery (cold rebuilds)
```

## 1. The official source is gone

`documents.gov.lk` — the Department of Government Printing's portal, and the
canonical index of Extraordinary Gazettes — no longer serves its archive. The
host returns an unconfigured Nginx Proxy Manager default page; the old
`/view/egz/egz_YYYY.html` index paths return a CMS 404.

There is currently **no authoritative enumeration** of Sri Lankan Extraordinary
Gazettes to check ourselves against. Any claim this project makes about
completeness is therefore bounded by that, permanently, until the source
returns.

## 2. The IRD listing is incomplete inside its own range

The listing covers gazettes 1439–2500 (April 2006 – August 2026). Eight
gazettes referenced by documents we hold fall *inside* that range and were
absent from `ird.gov.lk` entirely:

```
1439/01, 1439/02   siblings of 1439/03, which the listing DOES carry — same issue, same day
1441/17, 1441/18
1447/10, 1447/42
1680/21
1791/08
```

Not a parsing artefact: 123 URL spellings were probed across the 13 filename
conventions the IRD uses, and none hit, while the same probe found every
control. All seven that were recoverable turned out to be genuine tax
gazettes — Stamp Duty, Economic Service Charge, Inland Revenue, Finance.

> **`ird.gov.lk` answers `HEAD` with 404 and the same URL with 200 on `GET`.**
> Any existence check against that host must use a ranged `GET` (`curl -r 0-0`)
> or it will conclude the entire corpus is missing.

## 3. Why this matters more than the dangling edges themselves

A dangling reference is harmless on its own — we are not displaying a document
we do not hold. The dangerous case is its mirror image:

> **a gazette nobody lists, that rescinds one we hold.**

We would show it as `in_force` and be confidently wrong, and we cannot detect
it from our own data, by construction. The eight in-range omissions are proof
that the failure mode is real rather than theoretical.

That is why the disclosure below is not a placeholder for better data. It is
the honest floor, and it stays necessary even at 100% recovery.

## 4. What was recovered

The Internet Archive holds snapshots of `documents.gov.lk` under two layouts,
both of which put the gazette number in the path:

```
/files/egz/2012/12/1791-08_E.pdf
/Extgzt/2006/Pdf/Jun/1447-42/1447-42E.pdf
```

| | before | after |
|---|---:|---:|
| gazettes held | 137 | **144** |
| dangling references | 13 | 7 |
| in-range gaps | 8 | **1** |
| rule threads with a hole | 4 of 19 | **1 of 20** |
| gazettes reported in force inside a holed thread | 28 | **2** |

`1680/21` is the one in-range gap with no snapshot in the archive. The
remaining six references point at gazettes published before the listing begins
— a 1982 stamp duty order, a 2003 debits tax order — which no IRD source was
ever going to carry.

Recovered documents are stored with `source='web-archive'` and the snapshot URL
in `source_detail`. They are **never** indistinguishable from what the
department published, because the provenance is weaker and that is the reader's
to know.

## 5. Two bugs, both caught by the corpus rather than by tests

**Silent lookup failure.** The first version of `archive.find` wrapped the CDX
request in `except Exception: continue`, so the Internet Archive rate-limiting
us was reported as *"this gazette does not exist"*. A completeness check whose
network error is indistinguishable from an authoritative absence is worse than
none — it claims to have looked. With retries and backoff, one gazette that had
reported 0 snapshots reported 23.

**The wrong law.** Asking for `1439/01` also probes the unpadded `1439-1`, and
the CDX filter is a regex over the whole URL, so `1439-19` matched. A
**Provincial Councils Elections Act** gazette was ingested as an IRD tax
gazette. It passed every check that existed, because nothing compared the
number asked for with the number received.

Two guards now, deliberately independent:

1. **Exact number matching** on the URL, with every number a path claims having
   to agree — `/Extgzt/2006/Pdf/Mar/1439-19/1436-19e.pdf` is a real path where
   the directory and filename disagree.
2. **The document must confirm the URL.** The parsed header number is compared
   with the number requested and a mismatch rolls the backfill back, PDF
   included — `fetch.ensure` skips a download when the file exists, so leaving
   it would make the next attempt reuse the wrong document and report success.

A URL is a filing convention maintained by hand across two decades of a
government website. The printed header is the gazette.

## 5a. A third bug, caught by production: the recoveries were never written down

The seven recoveries lived only in the gitignored database. The nightly job
rebuilds from scratch, starting from the IRD listing — the one source
guaranteed *not* to contain them — so on its first unattended run
(2026-09-10, commit `3d8771f`) it:

- published a 137-gazette corpus: seven gazette pages disappeared, five rules
  lost the document they were rooted at, and because rule ids are assigned by
  position, 11 of the 20 `/rule/N/` URLs silently pointed at a different rule;
- rewrote `data/summaries.json` from a database that did not hold them,
  deleting seven paid-for summaries;
- reopened three rule chains that had been closed, so pages that could say
  "in force" went back to saying it conditionally;
- committed all of it as *"nightly gazette check, 0 new in the last 30 days"*.

No subscriber was misled: no feed entry id was new, so nothing re-notified;
six old entries quietly dropped out. It was found because the sitemap listed
159 URLs where the local build listed 167.

Every step did what it was asked on the input it had, so the fix is three
guards that do not depend on each other:

1. **`data/recovered.json`** records each recovery — exact archived URL, crawl
   timestamp, sha256 — and `vidhana restore` re-acquires them after `sync`. A
   Wayback `if_` capture at a fixed timestamp is immutable, so no archive
   search is involved, and the hash is checked before anything is ingested.
   All seven were re-fetched and came back byte-identical.
2. **`summaries export` merges and never prunes.** A document the rebuild
   failed to get back can no longer take its summary with it.
3. **`vidhana guard`** fails the nightly job, before it commits, if any gazette
   or summary would disappear. It does not know why, on purpose: a failed
   restore, a gazette the IRD delisted and a parser regression all look the
   same, and all want a human. Replayed against `3d8771f`, it refuses and
   names all seven.

The repair was produced by the fixed pipeline on a cold database, not by
`git checkout`, and every tracked artefact came out byte-identical to the last
state before the loss.

## 6. What the product now says

Search, at the point the claim is made:

```
1789/15  2012-12-18  [stamp-duty]  in force, but 2312/73 is the current document
                                   in this rule — history incomplete
                                   (2 referenced gazette(s) not held)
```

And in the feed, where a reader cannot ask a follow-up question:

> Caution: this rule's history is incomplete — 2 referenced gazette(s) are not
> in the corpus, so a change made by a document we do not hold would not appear
> here. Check the gazette itself before relying on this.

`chain_complete` is on every search result for any caller that wants to filter
or badge on it.

## 7. Standing limits

- **No authoritative source exists to verify against** while documents.gov.lk
  is down. Everything here is a lower bound on what is missing.
- **`1680/21` is still missing** and is referenced as rescinded by `1709/10`.
- **The invisible case remains invisible.** A gazette absent from every index
  we can reach, that rescinds one we hold, would not appear — which is exactly
  why "in force" is disclosed as conditional rather than asserted.
- **The Internet Archive is a mirror, not a registry.** Absence from it is not
  evidence that a gazette does not exist.
