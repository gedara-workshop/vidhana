# Vidhana

AI-powered search and alerts for Sri Lanka's government gazettes.

Part of [Gedara Workshop](https://github.com/gedara-workshop).

## The problem

Every time the Sri Lankan government changes a tax rule, a customs duty, a labour regulation, or almost anything else, it becomes official the moment a Gazette is published. Gazettes are numbered documents put out by the Department of Government Printing (and individual ministries), and they exist only as PDFs, sometimes real text, sometimes scanned images of paper, browsable by date but not searchable by topic.

A real example, and one that turned out to prove the point better than intended: [Gazette No. 2481/22](https://www.ird.gov.lk/en/publications/Gazette_Documents/2026_2481-22_E.pdf), issued March 27, 2026 by the Commissioner General of Inland Revenue, mandates a new standardised tax invoice format for every VAT-registered business. It said July 1, 2026. Then [Gazette No. 2500/106](https://www.ird.gov.lk/en/publications/Gazette_Documents/2026_2500_106_E.pdf) moved that date to October 1, 2026, in two sentences, in a separate PDF, that only makes sense if you already have the first one in front of you.

This README said July for a while, because that is what the document said when it was written. That is the problem, in miniature.

If you run a business and don't happen to check the right government page on the right week, you find out about this after you're already non-compliant, not because you did anything wrong, but because the only place this existed was a PDF nobody told you to read.

Vidhana reads these documents so you don't have to, and tells you the ones that actually affect you, in plain language, the day they're published.

## How it works

```
Government sites  ->  Scraper  ->  Text extraction  ->  LLM structuring  ->  Search + alerts
  (daily check)      (fetch new     (PDF text,          (gazette number,    (find what
                       PDFs)         selective OCR       date, authority,    affects you)
                                     for embedded        plain-English
                                     forms)              summary, tags)
                                            |
                                            v
                                    Amendment graph
                              (what amends what, what is
                               rescinded, what is in force)
```

Every summary links back to the original PDF. The summary is a convenience, the PDF is the source of truth, the two never get to drift apart.

The amendment graph is not a nice-to-have. Roughly half of the gazettes read in Phase 0 amend or rescind another gazette, and the current state of a rule frequently exists in no single document. Answering "what is the rule right now, and from when" is the part nobody else does.

Search is built on that graph rather than beside it. Asking the corpus about tax invoices turns up three gazettes that match equally well, because they are three drafts of one rule — and ranked by relevance alone, the one that comes first was rescinded in 2026. Every result therefore carries its standing, `--rules` collapses a thread into the document that is currently the rule, and `--as-of` answers what stood on a given date. Details in [PHASE3.md](PHASE3.md).

```
$ vidhana search "tax invoice"
  2463/05  2025-11-17  [vat]  rescinded by 2481/22 from 2026-07-01
  2481/22  2026-03-27  [vat]  in force, but 2500/106 is the current document in this rule
 2500/106  2026-08-06  [vat]  current document in a 3-document rule
```

## v0 scope

Starting narrow, on purpose. The general gazette archive spans multiple languages and inconsistent scan quality, that's a much bigger problem than a first version should try to solve. Vidhana v0 covers only **IRD tax and VAT gazettes**, a single ministry, a single topic, already published as clean, real-text PDFs. Wider ministries (Customs, Labour, general Extraordinary Gazettes) come later, once the pipeline is proven here.

One caveat found in Phase 0: the IRD listing is not purely tax and VAT, it carries the odd casino licensing regulation too, so v0 filters on subject rather than trusting the source.

## What Phase 0 found

Twenty-one real gazettes spanning 2007 to 2026, read end to end before any pipeline code. Full notes in [PHASE0.md](PHASE0.md) and [CORPUS-NOTES.md](CORPUS-NOTES.md). The findings that changed the plan:

- **Acquisition is easier than expected.** One request returns all 137 gazettes the listing carries, 2006 to 2026. No pagination, no JavaScript, no rate limiting to work around. Volume is 3 to 6 gazettes a year.
- **Almost nothing is a scan.** Nearly every document is real text back to 2007, so OCR isn't needed wholesale — just selectively, for six pages across three documents where the content is an image. One of those, a 2009 gazette, is a full-page scan that yielded a single byte of text until it was OCR'd.
- **The hard part is not the PDFs, it's the semantics.** Effective dates are frequently retroactive, sometimes several per document, and sometimes changed later by a different gazette. Dates sit in the middle and at the end of documents, not at the top.
- **Who a gazette affects is usually not written in it.** Nine of the twenty-one never say who they bind. That has to be inferred from the enabling Act — five across the sample, and twelve once all 137 were processed, which is still few enough to curate an Act-to-audience map by hand and hold the model to it.

## The source is incomplete, and the product says so

The IRD listing turned out to omit gazettes from inside its own date range — eight of them, including two published the same day as one it does carry. Worse, `documents.gov.lk`, the official index that would let anyone verify a gazette series, is offline, so there is no authoritative list to check against.

Seven of the eight were recovered from the Internet Archive and are stored with their provenance visible, never blended in with what the department published. That took rule threads with a hole in their history from 4 of 19 down to 1 of 20.

The part that does not go away: a gazette nobody indexes, which rescinds one we hold, would be invisible to us by construction. So wherever a rule's history has a hole, search and the feed **say so at the point the claim is made** rather than in a caveats page nobody opens. Full account in [COMPLETENESS.md](COMPLETENESS.md).

## Status

Early and building in public. This repo starts with the plan, not a finished product, commits will show the real build as it happens, evenings at a time. No live product yet, check the roadmap below for where things stand.

Stack is Python and SQLite. No service to run, the whole corpus is 144 documents.

## Roadmap

- [x] **Phase 0, Feasibility.** Read 15-20 real gazettes by hand, gauge language mix and scan quality, write summaries for 5 as an evaluation set.
- [x] **Phase 1, Acquisition.** Scraper for the IRD gazette listing page, fetch every gazette PDF, extract text, parse the header metadata, and build the amendment graph from the cross-references in the text.
- [x] **Phase 2, Structuring.** LLM pass over the cleaned text for a plain-English summary, the affected audience grounded on the enabling Act, effective dates, and tags.
- [x] **Phase 3, Search.** Full-text and topic search across the corpus, with the resolved state of a rule rather than just the documents that mention it.
- [x] **Phase 4, Alerts.** Daily check, notify on what is new and what it changes.

All four phases are done. The pipeline runs nightly and publishes Atom feeds: [everything](https://gedara-workshop.github.io/vidhana/feeds/all.xml), or one per subject — [income tax](https://gedara-workshop.github.io/vidhana/feeds/income-tax.xml), [VAT](https://gedara-workshop.github.io/vidhana/feeds/vat.xml), [stamp duty](https://gedara-workshop.github.io/vidhana/feeds/stamp-duty.xml). Method in [PHASE4.md](PHASE4.md).

Feeds are chosen over email deliberately: at 3-6 gazettes a year an inbox pipeline is mostly unused plumbing, and a feed holds no personal data, needs no server, and composes with everything else later. What happens after v0 depends on whether anyone actually subscribes, which no amount of building answers.
