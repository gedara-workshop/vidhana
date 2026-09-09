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
python3 -m vidhana backfill          # recover it
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
