# Vidhana

AI-powered search and alerts for Sri Lanka's government gazettes.

Part of [Gedara Workshop](https://github.com/gedara-workshop).

## The problem

Every time the Sri Lankan government changes a tax rule, a customs duty, a labour regulation, or almost anything else, it becomes official the moment a Gazette is published. Gazettes are numbered documents put out by the Department of Government Printing (and individual ministries), and they exist only as PDFs, sometimes real text, sometimes scanned images of paper, browsable by date but not searchable by topic.

A real example: [Gazette No. 2481/22](https://www.ird.gov.lk/en/publications/Gazette_Documents/2026_2481-22_E.pdf), issued March 27, 2026 by the Commissioner General of Inland Revenue, mandates a new standardised tax invoice format for every VAT-registered business starting July 1, 2026. If you run a business and don't happen to check the right government page on the right week, you find out about this after you're already non-compliant, not because you did anything wrong, but because the only place this existed was a PDF nobody told you to read.

Vidhana reads these documents so you don't have to, and tells you the ones that actually affect you, in plain language, the day they're published.

## Status

Early and building in public. This repo starts with the plan, not a finished product, commits will show the real build as it happens, evenings at a time. No live product yet, check the roadmap below for where things stand.

## How it works

```
Government sites  ->  Scraper  ->  Text extraction  ->  LLM structuring  ->  Search + alerts
  (daily check)      (fetch new     (PDF text, OCR      (gazette number,    (find what
                       PDFs)         fallback for        date, authority,    affects you)
                                     scans)               plain-English
                                                           summary, tags)
```

Every summary links back to the original PDF. The summary is a convenience, the PDF is the source of truth, the two never get to drift apart.

## v0 scope

Starting narrow, on purpose. The general gazette archive spans multiple languages and inconsistent scan quality, that's a much bigger problem than a first version should try to solve. Vidhana v0 covers only **IRD tax and VAT gazettes**, a single ministry, a single topic, already published as clean, real-text PDFs. Wider ministries (Customs, Labour, general Extraordinary Gazettes) come later, once the pipeline is proven here.

## Roadmap

- [ ] **Phase 0, Feasibility.** Read 15-20 real gazettes by hand, gauge language mix and scan quality, hand-write summaries for 5 as an evaluation set.
- [ ] **Phase 1, Acquisition.** Scraper for the IRD gazette listing page,
