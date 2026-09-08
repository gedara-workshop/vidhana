# Corpus notes — Claude's read of the 21 Phase 0 gazettes

A full read of every document in `data/manifest.csv`. This is the machine-side
read, kept separate from `PHASE0.md` §5–§6 so your own notes and the five
hand-written summaries stay an independent yardstick.

Structural findings live in `PHASE0.md` §3. This file is what the documents
*say*, what kind of instruments they are, and where extraction will actually hurt.

---

## 1. What's in the sample

| Gazette | Date | Authority | Instrument | Effective | Substance |
|---|---|---|---|---|---|
| `2500/106` | 06 Aug 2026 | CGIR | Amendment | immediate | Moves `2481/22`'s effective date from 01 Jul 2026 to **01 Oct 2026**. Two sentences. |
| `2481/22` | 27 Mar 2026 | CGIR | Order + Annexure | 01 Jul 2026 | New VAT tax invoice spec; makes `2463/05` optional then rescinds it. |
| `2463/05` | 17 Nov 2025 | CGIR | Order + Annexure | 01 Jan 2026 | First VAT tax invoice spec. Serial format `YYMMM_QQQQ_XXXXX`, 5-year retention, sample invoice form. |
| `2456/02` | 29 Sep 2025 | CGIR | Notification + Schedule | 01 Oct 2025 | **SVAT abolished**; Risk Based Refund Scheme replaces it. Low/medium/high risk tiers. Rescinds `1986/09`. Hard deadlines: SVAT 04 by 15 Oct, SVAT 06/07 by 20/30 Oct 2025. |
| `2443/30` | 01 Jul 2025 | CGIR | Order + Schedule | 01 Oct 2025 | **VAT on non-resident digital services.** Registration threshold Rs 60M/12mo or Rs 15M/3mo. Names Netflix-class platforms: PayPal, Stripe, OpenSea, Binance. |
| `2429/39` | 27 Mar 2025 | Min. Finance | Order (amend) | 01 Apr 2025 | Stamp duty on leases/hire: Rs 20 per Rs 1,000; Rs 10 for hire-purchase. Replaces item 9 of `1465/19` schedule. |
| `2414/14` | 11 Dec 2024 | CGIR | Regulations + Schedule | 01 Jan 2025 | Tax Clearance Certificate for outward remittances. Has a **Negative List** of exempt remittance types. ⚠ Form pages are images. |
| `2378/33` | 04 Apr 2024 | CGIR | Notice + Schedule | none stated | Tax payments only by cash deposit, pay order/draft, or Online Tax Payments Platform. |
| `2376/25` | 21 Mar 2024 | Min. Finance | Regulation + 2 Schedules | 01 Apr 2024 | **Mass data-sharing mandate.** Registrar-General, Companies, Motor Traffic, banks, CSE must feed IRD's RAMIS risk module. Some data only from 01 Jul 2024. |
| `2363/22` | 19 Dec 2023 | Min. Finance | Order (amend) | 01 Jan 2024 | **VAT rate to 18%.** Amends `2282/26`, rescinds `2295/08`. One page. |
| `2334/21` | 31 May 2023 | Min. Finance + CGIR consent | Notice + Schedule | **two dates** | Compulsory income-tax registration. Part A (professionals, vehicle owners, property buyers) from 01 Jun 2023; **Part B — every resident aged 18+** from 01 Jan 2024. |
| `2316/13` | 24 Jan 2023 | CGIR | Order + Schedule | **01 Oct 2022 (retroactive)** | VAT on financial services calculation. Rescinds `1868/10`. NBT→SSCL, IRA 2006→2017. |
| `2312/73` | 31 Dec 2022 | Min. Finance | Order (amend) | not stated | Adds item 37 (Colombo Port City leases) to `1465/20` schedule, "as last amended by `2149/18`". |
| `2295/10` | 31 Aug 2022 | Min. Finance | Regulations | not stated | ⚠ **Casino business licensing** — not a tax instrument. See §4. |
| `2217/07` | 02 Mar 2021 | Min. Finance | Regulations | **01 Apr 2020 (retroactive)** | Transfer pricing, 43pp. Rescinds `2104/04`. OECD-style Master/Local file and CbC tables. |
| `2149/18` | 14 Nov 2019 | Min. Finance | Order (amend) | not stated | Adds item 36 (government/UDA leases) to `1465/20`, "as last amended by `2007/24`". |
| `2064/54` | 01 Apr 2018 | CGIR | Regulations + Schedule | 01 Apr 2018 | Levies not deductible in computing income (ESC, NBT on financial services, crop insurance levy, "supper gain tax"). |
| `1991/35` | 02 Nov 2016 | Min. Finance | Regulations + Schedule | not stated | RAMIS: electronic filing, Tax Agent definition, e-service rules. |
| `1868/10` | 23 Jun 2014 | CGIR | Order + Schedule | **01 Jan 2014 (retroactive)** | VAT on financial services at 12% + 8% Central Bank fund. Later rescinded by `2316/13`. |
| `1728/13` | 19 Oct 2011 | CGIR | Notice (amend) | not stated | Amends `1704/18`: pension/provident funds must hold ≥40% in named state banks or government securities. |
| `1487/03` | 05 Mar 2007 | Min. Finance | Regulations | none stated | Authorised Representative registration — eligibility, disqualification, removal. |

---

## 2. Instrument taxonomy

Four recurring shapes, and they behave differently enough to matter:

1. **Standalone substantive** (`2443/30`, `2456/02`, `2376/25`, `1487/03`) — self-contained. Safe to summarise alone.
2. **Full replacement** (`2316/13` over `1868/10`, `2217/07` over `2104/04`) — restates an entire scheme and rescinds the predecessor. Safe alone, but the old one must be marked dead.
3. **Surgical amendment** (`2149/18`, `2312/73`, `2429/39`, `1728/13`, `2363/22`) — "substitute paragraph (i) of item (2) of the Schedule". **Meaningless alone.** The resulting rule exists in no single document.
4. **Metadata-only amendment** (`2500/106`) — changes one date in an earlier gazette. Most dangerous to summarise standalone, because it reads as trivial while silently invalidating the earlier summary.

Roughly **half the sample is type 3 or 4.** A pipeline that treats gazettes as independent documents gets half this corpus wrong.

---

## 3. The amendment chains, reconstructed

Three chains are visible inside the sample alone:

```
Stamp Duty s.5     1465/20 (2006) → 2007/24 (2017) → 2149/18 (2019, +item 36) → 2312/73 (2022, +item 37)
Stamp Duty s.3     1465/19 (2006) → 2104/05 (2018) → 2429/39 (2025, replaces item 9)
VAT fin. services  1868/10 (2014) → 2316/13 (2023, full replacement)
VAT tax invoice    2463/05 (2025) → 2481/22 (2026) → 2500/106 (2026, date only)
```

**`as last amended by` is a machine-readable back-pointer.** It appears verbatim
in `2149/18`, `2312/73`, `2429/39` and `2316/13`, and always names the immediately
preceding amendment. Chains can be walked backwards from any node without
guessing.

**All 12 cross-references in the sample resolve to gazettes present in the IRD
listing** — after zero-padding normalisation. Nothing dangles. Strong evidence
the listing is self-contained for this domain and the amendment graph closes.

But normalisation is mandatory: references are written `No. 2104/4`, `No. 1986/9`,
`No. 2217/7` while the listing has `2104/04`, `1986/09`, `2217/07`. Without
normalising, 5 of 12 edges silently fail.

---

## 4. ⚠ The v0 scope assumption needs a caveat

`2295/10` is **casino licensing regulation** under the Casino Business
(Regulation) Act — licence applications, compliance officers, surrender of
licences. It is on the IRD gazette page because IRD collects casino levies, but
it is not a tax or VAT instrument.

Classifying the full 137-row listing by description:

| Subject | Count |
|---|---|
| Income Tax / Inland Revenue Act | 39 |
| **Description too terse to classify** | **34** |
| VAT | 31 |
| Stamp Duty | 23 |
| Economic Service Charge | 5 |
| Betting & Gaming / Casino | 2 |
| SSCL / NBT / other levies | 3 |

Two things follow:

1. **"The IRD listing" ≠ "tax and VAT gazettes".** v0 needs a *content* filter, not just a source filter.
2. **The listing description is often useless for classification** — "Notice under Paragraph 10 of Sixth Schedule", "Notice under Section 5,10, First Schedule and Third Schedule". 34 of 137 say nothing about subject matter. Classification must read the PDF's Act line, not the listing text.

---

## 5. Field-by-field extraction reality

**Gazette number** — reliable from the `No. NNNN/NN` header line, but normalise padding and prefer the listing. `$` appears for `/` in the Sinhala line.

**Publication date** — reliable from the same header line. ⚠ **Never take it from the running page header**: `2149/18` says `16.10.2019` in its running header but is dated 14 Nov 2019; `2312/73` says `13.12.2022` but is dated 31 Dec 2022; `2064/54` says `05.03.2018` but is dated 01 Apr 2018. The running header is a template artifact and is wrong roughly half the time.

**Signature date** — a *third* distinct date, usually days before publication, and not always sane: `1728/13` is published 19 Oct 2011 but signed "21st October, 2011", two days *after*.

**Effective date** — the hard one, and the one the product depends on:
- Often absent entirely (`2378/33`, `1991/35`, `1487/03`, `1728/13`, `2312/73`).
- Often **retroactive**: `2316/13` published Jan 2023, effective Oct 2022; `2217/07` published Mar 2021, effective Apr 2020 (11 months back); `1868/10` published Jun 2014, effective Jan 2014.
- Sometimes **plural within one document**: `2334/21` Part A from 01 Jun 2023, Part B from 01 Jan 2024. `2376/25` from 01 Apr 2024 with some obligations from 01 Jul 2024.
- Sometimes **changed later by another gazette** (`2500/106`).

  → `effective_date` cannot be a scalar column. It is per-provision, resolvable, and mutable.

**Authority** — not always IRD. Commissioner General signs Notices and most Regulations; **Minister of Finance** signs Orders under the Acts (`2363/22`, `2429/39`, `2149/18`, `2312/73`, `2376/25`, `2295/10`, `1487/03`). `2334/21` is the Minister *with the consent of* the CGIR — two authorities. Ministerial titles drift ("Minister of Finance" → "…, Economic Stabilization and National Policies" → "…, Planning and Economic Development") for the same office, so entity resolution is needed.

**Enabling Act** — always present, but casing is arbitrary (`inland revenue act, no. 24 of 2017` lowercase in `2378/33`, `stAmp duty` mixed in `2312/73`). Match case-insensitively.

**Affected population** — ⚠ **absent from most documents.** See §5b: 9 of 21 state no audience at all, and only ~5 state one plainly. This is an inference task grounded on the enabling Act, not an extraction task. Where vocabulary does appear it is reusable as tags: "every registered person", "withholding agents", "licensed commercial banks and authorized dealers", "non-resident person", "specified institutions", "eligible exporter".

---

## 5b. ⚠ The affected population is usually NOT in the document

*Found by Dinal during his own read, then verified against the corpus.*

He noticed he couldn't find who a gazette affects. That is correct, and it is the
most consequential finding in Phase 0.

Searching all 21 documents for any sentence that states scope — "shall apply to",
"applicable to", "every registered person", "shall comply with":

- **9 of 21 contain no applicability statement at all**: `1728/13`, `2064/54`,
  `2149/18`, `2312/73`, `2363/22`, `2376/25`, `2378/33`, `2429/39`, `2500/106`.
- Of the matches in the remaining 12, most are **incidental** — a "person who"
  inside a definition (`1487/03`'s audit service grades, `2295/10`'s "key
  employee", `2217/07`'s penal provisions), not a scope statement.
- **Only about 5 documents state their audience plainly**: `2414/14` ("Every
  Licensed Commercial Banks and Authorized Dealers … shall comply"), `2456/02`
  ("This procedure shall apply to eligible persons …"), `2443/30` ("A non-resident
  person who supplies services … must register"), and `2463/05` / `2481/22`
  (audience embedded mid-sentence in the operative clause).

The clearest case is `2363/22`: one page, raises VAT to 18%, affects every
business and consumer in the country, and **never names anyone**. It reads as a
textual substitution into an earlier order.

> **Consequence — this changes the pipeline shape.** "Who does this affect" is
> not an extraction task. It cannot be pulled from the text because in most
> documents it is not in the text. It is an **inference** requiring knowledge the
> document does not carry: what the enabling Act governs and who it binds.
>
> That is precisely where an LLM earns its place — and precisely where it will
> hallucinate confidently and unfalsifiably.

**The grounding that makes this tractable:** the corpus rests on a *very* small
set of enabling Acts. Across all 21 documents there are only **five**:

| Enabling Act | Docs | Who it binds |
|---|---|---|
| Value Added Tax Act, No. 14 of 2002 | 8 | VAT-registered persons; consumers via price |
| Inland Revenue Act, No. 24 of 2017 | 6 | Income taxpayers, withholding agents, employers |
| Inland Revenue Act, No. 10 of 2006 | 3 | (predecessor of the above) |
| Stamp Duty (Special Provisions) Act, No. 12 of 2006 | 3 | Parties to leases, transfers, instruments |
| Casino Business (Regulation) Act, No. 17 of 2010 | 1 | Casino licence holders |

A **hand-curated Act (+ section) → audience map** would ground the audience field
for essentially the whole corpus, is auditable, and takes an afternoon. Prefer it
over free-form LLM inference, and let the model only *narrow* within the Act's
audience using the document text — never invent an audience the Act doesn't bind.

## 5c. Dates are scattered through the body, not clustered at the top

*Also from Dinal's read: "the dates … in mid doc also".*

Confirmed. Mapping every date mention to its position through each document
(running headers excluded, since they repeat the publication date on every page):

- `2500/106` has **no date at all in its first 20%** — its operative content, the
  July→October change, sits mid-document.
- `2456/02` carries **21 date mentions, 13 distinct**, and the actionable
  transitional deadlines (15, 20, 30 October, 10 November) are in the **final
  fifth**.
- `2334/21`'s two effective dates are at roughly 80% and 90% through.
- `2363/22`'s operative "with effect from January 01, 2024" appears twice, at
  ~70% and ~90%.

> **Consequence:** any "read the first page / first N characters" strategy will
> reliably capture the *signature* date and miss the *effective* date and every
> deadline. The whole document must reach the extraction step, and dates must be
> collected with their surrounding clause so "effective from", "rescinded with
> effect from", "on or before" and "signed on" stay distinguishable.

## 6. Where a fluent summary would go wrong

Concrete traps found in this sample:

- **`2463/05` vs `2481/22`** look near-identical and differ in ways that matter: telephone number goes **mandatory → optional**, TIN gains a "nine (9) digits" spec, invoice title changes `"Tax Invoice"` → `"TAX INVOICE"`. A summary saying "requires a standard tax invoice format" is true of both and useful for neither.
- **`2500/106` reads as trivial** — two sentences amending a date — but it is the only reason the current answer is October and not July.
- **Page 1 is often not enough.** `2334/21`'s page 1 says only "as specified in PART A or PART B of the Schedule"; the substance — including "every resident aged 18 or over" — is on page 2. Same for `2378/33`, `2414/14`, `2316/13`.
- **Numbers written as text fractions**: `12 1/2%`, `6 2/3%` in the depreciation tables. A naive numeric parser reads `12`, `1`, `2`.
- **Rescission and effect can have different dates**: `2481/22` makes `2463/05` "optional" immediately but rescinds it only from 01 Jul 2026 — a window where both are live.

---

## 7. Text-quality defects to expect

Present in the *original* documents, not introduced by extraction — preserve when quoting, but don't rely on exact string matching:

- Typos in headings and body: `Notie under Secton 217`, `Notificaiton`, `Notificiaton`, `registerd`, `Turnovr`, `Sevices`, `softweare`, `supper gain tax`, `reffered`, `remiting`, `specilized`.
- **A corrupted email address**: `cd@ird.gov.Ik` in `2414/14` — capital `I` for lowercase `l`. Never extract contact details without validation.
- `I` rendered as `1`: "No. 12 of 2006, 1, Anura Kumara Dissanayake" in `2429/39`.
- Spurious intra-word spaces: `whic h`, `else where` (`1487/03`).
- Names wrap across lines in signature blocks with embedded tabs (`2316/13`).
- **Two different legacy Sinhala encodings**, not one: 2007-era renders as Latin-1 accented text (`Êòé Èâ¨å`), 2011-onward as ASCII symbol soup (`Y%S ,xld`). A boilerplate stripper must cover both.
- Formulas and multi-column arithmetic layouts (`2316/13`, `1868/10` value-addition tables) degrade into unparseable soup. Treat as opaque blocks; do not attempt structured extraction.

---

## 8. What this implies for Phase 1

- Scrape the listing, but **key every record on the normalised listing number**.
- Store the raw PDF and the `-layout` text; strip the boilerplate and running
  headers *before* anything sees it.
- Extract cross-references at ingest and build the amendment graph early — it is
  cheap here (the graph closes, 12/12) and it is what makes the product correct
  rather than merely fluent.
- Flag image-bearing low-text pages for OCR rather than OCR-ing everything.
- Treat `effective_date` as derived state, not a scraped field.
