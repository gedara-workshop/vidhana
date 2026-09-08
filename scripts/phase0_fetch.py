#!/usr/bin/env python3
"""Phase 0 helper: fetch a hand-picked sample of IRD gazette PDFs for manual reading.

This is NOT the Phase 1 scraper. It exists only to pull a reading sample and record
what came back, so Phase 0 findings are reproducible. Deliberately dumb and serial.

  python3 scripts/phase0_fetch.py --listing        # re-parse the live listing page
  python3 scripts/phase0_fetch.py --sample         # download the Phase 0 sample
"""
import argparse, csv, hashlib, html, json, os, re, subprocess, sys, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTING_URL = "https://www.ird.gov.lk/en/publications/sitepages/gazette.aspx?menuid=1602"
LISTING_JSON = os.path.join(ROOT, "data", "listing", "gazette-listing.json")
PDF_DIR = os.path.join(ROOT, "data", "gazettes")
MANIFEST = os.path.join(ROOT, "data", "manifest.csv")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124 Safari/537.36"

# Phase 0 reading sample: weighted to recent (v0 scope) with older years sampled
# to gauge how far back clean text survives.
SAMPLE = [
    "2500/106", "2481/22",                        # 2026
    "2463/05", "2456/02", "2443/30", "2429/39",   # 2025
    "2414/14", "2378/33", "2376/25",              # 2024
    "2363/22", "2334/21", "2316/13",              # 2023
    "2312/73", "2295/10",                         # 2022
    "2217/07",                                    # 2021 (TP_ filename variant)
    "2149/18",                                    # 2019
    "2064/54",                                    # 2018
    "1991/35",                                    # 2016
    "1868/10",                                    # 2014 (_(E) filename variant)
    "1728/13",                                    # 2011
    "1487/03",                                    # 2007 (oldest, scan-quality probe)
]


def get(url, binary=False):
    req = urllib.request.Request(quote_url(url), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def quote_url(url):
    """IRD hrefs contain raw spaces; encode the path but leave the rest alone."""
    p = urllib.parse.urlsplit(url)
    return urllib.parse.urlunsplit(
        (p.scheme, p.netloc, urllib.parse.quote(p.path, safe="/%"), p.query, p.fragment)
    )


def parse_listing(page):
    """The page is one flat document: an <h4>YEAR</h4> per year, each followed by a
    3-column table (date / no / description+link). Years collapse client-side only,
    so every row is present in the HTML. There is no pagination."""
    rows = []
    parts = re.split(r"<h4>.*?</i>\s*(\d{4})\s*</h4>", page, flags=re.S)
    for i in range(1, len(parts), 2):
        year, body = parts[i], parts[i + 1].split("<h4>")[0]
        for tr in re.findall(r"<tr>(.*?)</tr>", body, re.S):
            tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
            if len(tds) < 3:
                continue
            strip = lambda s: re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", s))).strip()
            m = re.search(r'href="([^"]+)"', tds[2])
            row = dict(year=year, date=strip(tds[0]), no=strip(tds[1]),
                       url=m.group(1) if m else None, desc=strip(tds[2]))
            if row["no"] or row["url"]:      # skip the one empty <tr> under 2006
                rows.append(row)
    return rows


def slug(no, date):
    """Stable local name: gazette number is the real identity, filenames upstream are not."""
    return f"{no.replace('/', '-')}_{date.replace(' ', '')}"


def probe(path):
    """What did we actually get: real text layer, or a scan?"""
    def run(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
        except Exception:
            return ""
    info = run(["pdfinfo", path])
    pages = re.search(r"^Pages:\s*(\d+)", info, re.M)
    text = run(["pdftotext", "-q", path, "-"])
    imgs = run(["pdfimages", "-list", path])
    return dict(
        pages=pages.group(1) if pages else "",
        producer=(re.search(r"^Producer:\s*(.+)$", info, re.M) or [None, ""])[1].strip(),
        chars=len(text.strip()),
        images=max(0, len(imgs.strip().splitlines()) - 2),
        text_layer="yes" if len(text.strip()) > 200 else "no/scanned",
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--listing", action="store_true", help="re-fetch and re-parse the listing page")
    ap.add_argument("--sample", action="store_true", help="download the Phase 0 sample")
    a = ap.parse_args()

    if a.listing:
        rows = parse_listing(get(LISTING_URL))
        os.makedirs(os.path.dirname(LISTING_JSON), exist_ok=True)
        json.dump(rows, open(LISTING_JSON, "w"), indent=1)
        print(f"listing: {len(rows)} rows -> {LISTING_JSON}")

    if a.sample:
        rows = {r["no"]: r for r in json.load(open(LISTING_JSON))}
        os.makedirs(PDF_DIR, exist_ok=True)
        out = []
        for no in SAMPLE:
            r = rows.get(no)
            if not r or not r["url"]:
                print(f"  MISS {no}: not in listing"); continue
            name = slug(no, r["date"]) + ".pdf"
            path = os.path.join(PDF_DIR, name)
            if not os.path.exists(path):
                try:
                    open(path, "wb").write(get(r["url"], binary=True))
                except Exception as e:
                    print(f"  FAIL {no}: {e}"); continue
                time.sleep(1.5)                      # be polite to a government host
            p = probe(path)
            out.append(dict(gazette_no=no, date=r["date"], year=r["year"], file=name,
                            bytes=os.path.getsize(path),
                            sha256=hashlib.sha256(open(path, "rb").read()).hexdigest()[:16],
                            source_url=r["url"], desc=r["desc"], **p))
            print(f"  ok {no:>10}  {p['pages']:>3}p  text={p['text_layer']:<10} chars={p['chars']}")
        with open(MANIFEST, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(out[0].keys()))
            w.writeheader(); w.writerows(out)
        print(f"\nmanifest: {len(out)} rows -> {MANIFEST}")


if __name__ == "__main__":
    main()
