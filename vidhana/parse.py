"""Pull structured metadata out of the cleaned gazette text.

Everything here is anchored on patterns validated against the 21-document Phase 0
sample. Where a rule is deliberately tolerant, the comment says which real
document forced it.
"""
from __future__ import annotations

import datetime as dt
import re

from .util import normalise_no, parse_date

# "No. 2481/22 - FRIDAY, MARCH 27, 2026". Tolerant because the corpus contains:
#   'No. 2456 /02'                    (stray space inside the number)
#   'No. 2064/54 - SUNDAY, APRIL 01 2018'  (no comma before the year)
#   'thursday, march 27, 2025'        (arbitrary casing)
#   'No. 1868/10 — MONDAY, JUNE 23'   (em dash)
# A naive ^No\. (\S+) - (.+, \d{4})$ matches only 19 of 21; this matches 21 of 21.
HEADER_RE = re.compile(
    r"^[ \t]*No\.\s*(\d{3,4}\s*[/$]\s*\d{1,3})\s*[-–—]\s*(.+?,?\s*\d{4})[ \t]*$",
    re.M | re.I)

# The Act line sits between "Government Notifications" and the operative paragraph.
ACT_RE = re.compile(
    r"([A-Za-z()'’ ]{5,70}?ACT),?\s*No\.?\s*(\d+)\s*OF\s*(\d{4})", re.I)

# Explicit alternation rather than a greedy trailing class: the office is renamed
# every few years ("Minister of Finance" -> "..., Economic Stabilization and
# National Policies" -> "..., Planning and Economic Development") and a loose
# pattern swallows the sentence that follows it.
ROLE_RE = re.compile(
    r"((?:Acting\s+)?Commissioner[- ]General of Inland Revenue"
    r"|(?:Acting\s+)?Minister of Finance"
    r"(?:\s*,?\s*Economic Stabilization and National Policies"
    r"|\s*,?\s*Planning and Economic Development"
    r"|\s+and Planning)?"
    # Older gazettes (2006-2015) are signed by the President acting under
    # Article 44(2) of the Constitution, and the Tax Appeals Commission rules by
    # its Chairman. Omitting these cost 26 of 137 signatories.
    # "President," in the operative clause, "President." in the signature block.
    r"|President(?=\s*[,.]|\s*$)"
    r"|Chairman[A-Za-z, ]{0,40}Commission)", re.I)

# Cross-references. The corpus writes these many ways; capture the relation word
# that precedes or follows so the edge can be typed rather than just "cites".
# Note the misspellings: the corpus prints "Notificaiton" (2312/73, twice) and
# "Notificiaton" (2149/18). Matching only the correct spelling loses real edges.
REF_RE = re.compile(
    r"Gaz(?:ette)?\.?\s*(?:Ex(?:traordinary)?\.?\s*)?"
    r"(?:Notification|Notificaiton|Notificiaton|Order|Ordinance)?\s*"
    r"No\.?\s*(?P<no>\d{3,4}\s*[/_$]\s*\d{1,3})",
    re.I)

_RESCIND = r"rescind|revoke|repeal"
_AMEND = r"amend|substitut|addition of|deletion of"
# Relation priority per edge, most specific first.
_RANK = {"last_amended_by": 0, "rescinds": 1, "amends": 2, "cites": 3}

# Date kinds, most specific first — "rescinded with effect from" must beat "effect from".
DATE_KINDS = (
    ("rescind_effective", r"(?:rescind|revoke|repeal)\w*\s+(?:[^.\n]{0,60}?)?with\s+effect\s+from"),
    # The metadata-only amendment form (2500/106):
    #   The effective date of "July 01, 2026", is hereby amended as "October 01, 2026"
    # Neither date is this document's own effective date. October is the value it
    # *sets on another gazette*, July is the value it replaces. Both patterns are
    # anchored to the end of the window so they only fire on the date that
    # immediately follows the phrase.
    ("sets_effective_date",     r"amended\s+(?:as|to)\s*[\u201c\u2018\"']?\s*$"),
    ("replaces_effective_date", r"effective\s+date\s+of\s*[\u201c\u2018\"']?\s*$"),
    ("effective",         r"(?:with\s+effect\s+from|effective\s+from|come\s+into\s+effect\s+from"
                          r"|shall\s+come\s+into\s+(?:force|operation)\s+(?:on|from)"
                          r"|operate\s+effective\s+from|effective\s+from\s+the\s+taxable\s+period"
                          r"|with\s+effects\s+from)"),
    ("deadline",         r"(?:on\s+or\s+before|not\s+later\s+than|no\s+later\s+than|by\s+the\s+twentieth)"),
)
# The operative clause: "I, <name>, <office>, do by this Order ... with effect
# from <date>". It is the document's own act, so a date it carries is this
# document's effective date — unlike an effective date inside a schedule, a
# transitional provision, or another instrument reproduced in full, all of
# which the minimum used to pick. 1791/08 (published December 2012) reproduces
# regulations that "shall come into operation on September 1, 2003"; its own
# order is "with effect from January 1, 2013". 1868/10 says it in words: "with
# effect from 01.01.2014 subject to the specific dates mentioned in the
# Schedule". The lookback is wide because the clause names the Act and the
# official before it reaches the date; 400 characters holds the longest in the
# corpus (1868/10) without reaching into a schedule.
OPERATIVE = re.compile(r"\bdo\s+(?:by\s+th(?:is|ese)|hereby)\b", re.I)
OPERATIVE_REACH = 400

# "with effect from the mid night of 31st December, 2006" is the first moment
# of 1 January 2007, which 1478/08 spells out in the same breath
# ("31st December, 2006/1st January, 2007").
MIDNIGHT = re.compile(r"mid\s*-?\s*night\s+of\s*(?:the\s+)?$", re.I)

_MONTH = (r"(?:January|February|March|April|May|June|July|August|September|October|"
          r"November|December)")
DATE_TOKEN = re.compile(
    rf"({_MONTH}\s+\d{{1,2}},?\s+\d{{4}}|\d{{1,2}}(?:st|nd|rd|th)?\s+{_MONTH},?\s+\d{{4}}"
    rf"|\d{{1,2}}[./]\d{{1,2}}[./]\d{{4}}|\d{{4}}[.']\d{{1,2}}[.']\d{{1,2}})", re.I)


def header(text: str) -> tuple[str | None, str | None]:
    """-> (gazette number as printed, ISO publication date). Never from the running
    page header: that carries a template date and is wrong in 3 of 21 documents."""
    m = HEADER_RE.search(text)
    if not m:
        return None, None
    return normalise_no(m.group(1)), parse_date(m.group(2))


def enabling_act(text: str) -> tuple[str | None, str | None]:
    head = text.split("Government Notifications", 1)
    window = head[1][:600] if len(head) > 1 else text[:900]
    m = ACT_RE.search(window)
    if not m:
        return None, None
    name = re.sub(r"\s+", " ", m.group(1)).strip().title()
    name = re.sub(r"^(The|By|Under|Of|In|And|To|A Of)\s+", "", name)
    return name, f"{int(m.group(2))} of {m.group(3)}"


def authority(text: str) -> tuple[str | None, str | None]:
    """Signatory name and role.

    The reliable anchor is "<NAME>, <ROLE>", which appears both in the operative
    sentence ("I, Rukdevi Perpetua Himali Fernando, Commissioner General of Inland
    Revenue, do by this order ...") and in the signature block. Text is
    whitespace-normalised first because names wrap across lines — 2316/13 splits
    "Don Ranjith Sisirakumara / Hapuarachchi" over two lines with a tab.

    Note the `[I1]` in the operative form: 2429/39 prints "1," for "I,".
    """
    flat = re.sub(r"\s+", " ", text)
    m = re.search(r"\b[I1]\s*,\s*([A-Z][A-Za-z.\-' ]{4,60}?)\s*,\s*"
                  r"(?:Acting\s+)?(?=Commissioner|Minister|President|Chairman)", flat)
    name = m.group(1).strip() if m else None
    if not name:
        # No operative "I, ..." form (1487/03, 1991/35, 2217/07 are drafted
        # impersonally); fall back to the signature block.
        m2 = re.search(r"([A-Z][A-Za-z.\-' ]{4,60}?)\s*,\s*"
                       r"(?:Acting\s+)?(?=Commissioner[- ]General of Inland Revenue"
                       r"|Minister of Finance|President\s*[,.]|Chairman)", flat)
        name = m2.group(1).strip() if m2 else None
    if name:
        # The fallback can run backwards across a sentence boundary
        # ("... read with section 105B by the said Act. RAVI KARUNANAYAKE").
        # Drop any leading remnant ending in a real word + full stop; initials
        # like "D. M. L. I. Dissanayake" are single letters and survive.
        name = re.sub(r"^.*?\b\w{2,}\.\s+", "", name).strip()
        if name.isupper():
            name = name.title()
        if len(name) < 4:
            name = None

    r = ROLE_RE.search(flat)
    role = re.sub(r"\s+", " ", r.group(1)).strip().rstrip(".,").title() if r else None
    return name, role


# Abbreviations whose full stop does not end a sentence. Legal citations are full
# of them ("No. 12 of 2006", "Sec. 5"), so a naive split on ". " is useless here.
_ABBREV = {"no", "nos", "sec", "secs", "ex", "art", "cap", "vol", "pt", "reg"}


def _current_sentence(pre: str) -> str:
    """Trim `pre` back to the sentence containing the reference.

    Without this, a preceding sentence lends its verb to the wrong edge: in
    2481/22 the sentence before the reference to 2463/05 happens to contain
    "may amend the format ... from time to time", which would type the edge as
    `amends` when the document actually rescinds 2463/05.
    """
    cut = 0
    for m in re.finditer(r"\.\s+(?=[A-Z\u201c\"])", pre):
        word = re.search(r"([A-Za-z]+)\.$", pre[:m.end()].rstrip())
        if not word:
            continue
        w = word.group(1)
        if len(w) > 1 and w.lower() not in _ABBREV:
            cut = m.end()
    return pre[cut:]


def _relation(pre: str, post: str) -> str:
    """Type an edge from the words around the reference.

    The verb sits on either side depending on drafting style:
      before -> "do by this Order amend the order ... published in ... No. 1465/20"
      after  -> "Gazette Notification No. 1986/9 dated September 27, 2016 are rescinded"

    "as last amended by" is checked first and only close to the reference, because
    a single sentence often carries both ("amend the order ... published in
    No. 1465/20, as last amended by ... No. 2149/18") and each half belongs to a
    different edge. Preceding words win over following ones, so a later sentence's
    verb cannot capture this reference.
    """
    pre = _current_sentence(pre)
    if re.search(r"as\s+last\s+amended\s+by[^.]{0,60}$", pre, re.I):
        return "last_amended_by"
    if re.search(_RESCIND, pre, re.I):
        return "rescinds"
    if re.search(_AMEND, pre, re.I):
        return "amends"
    if re.search(_RESCIND, post, re.I):
        return "rescinds"
    if re.search(_AMEND, post, re.I):
        return "amends"
    return "cites"


def references(text: str, self_no: str | None = None) -> list[dict]:
    """Typed edges of the amendment graph, one per referenced gazette.

    Numbers are normalised: the corpus cites 'No. 2104/4' and 'No. 1986/9' where
    the listing has '2104/04' and '1986/09'. Without normalising, 5 of the 12
    references in the Phase 0 sample fail to connect.
    """
    best: dict[str, dict] = {}
    for m in REF_RE.finditer(text):
        dst = normalise_no(m.group("no").replace("_", "/"))
        if not dst or dst == self_no:
            continue
        pre = re.sub(r"\s+", " ", text[max(0, m.start() - 260):m.start()])
        post = re.sub(r"\s+", " ", text[m.end():m.end() + 170])
        rel = _relation(pre, post)
        raw = re.sub(r"\s+", " ", (pre[-90:] + m.group(0) + post[:70])).strip()
        cur = best.get(dst)
        if cur is None or _RANK[rel] < _RANK[cur["relation"]]:
            best[dst] = dict(dst_no=dst, relation=rel, raw=raw)
    return list(best.values())


def dates(text: str) -> list[dict]:
    """Typed dates with the clause they came from.

    Phase 0: effective dates are frequently retroactive, sometimes plural in one
    document (2334/21 has two, seven months apart), and often sit in the middle or
    at the end rather than the top — so the whole text is scanned, not the head.
    """
    out: dict[tuple[str, str], dict] = {}
    for m in DATE_TOKEN.finditer(text):
        iso = parse_date(m.group(1))
        if not iso:
            continue
        window = re.sub(r"\s+", " ", text[max(0, m.start() - 130):m.start()]).lower()

        # A date immediately after a gazette citation belongs to the *cited*
        # document, not this one. 2217/07 reads "operate effective from April 1,
        # 2020 and rescind the Regulations published in ... No. 2104/4 of
        # December 31, 2018" — taking the minimum of everything typed
        # `effective` picked 2018, the rescinded gazette's own date.
        if re.search(r"no\.?\s*\d{3,4}\s*[/$]\s*\d{1,3}\s*,?\s*(?:of|dated)\s*$", window):
            continue

        # Square brackets mark historical asides, not this document's operative
        # date: 2316/13 carries "[With effect from 01.01.2012, any specified
        # institution ...]" while itself taking effect in October 2022.
        opened = text.rfind("[", 0, m.start())
        if opened != -1 and text.find("]", opened) > m.start():
            continue

        kind = None
        for k, pat in DATE_KINDS:
            if re.search(pat, window, re.I):
                kind = k
                break
        if not kind:
            continue
        if kind == "effective":
            reach = re.sub(r"\s+", " ", text[max(0, m.start() - OPERATIVE_REACH):m.start()])
            if OPERATIVE.search(reach):
                kind = "operative"
        if kind in ("effective", "operative", "rescind_effective") and MIDNIGHT.search(window):
            iso = (dt.date.fromisoformat(iso) + dt.timedelta(days=1)).isoformat()
        ctx = re.sub(r"\s+", " ",
                     text[max(0, m.start() - 110):m.end() + 30]).strip()
        out.setdefault((kind, iso), dict(kind=kind, date=iso, context=ctx[:300]))
    return list(out.values())


SUBJECTS = (
    ("vat",          r"value added tax"),
    ("income-tax",   r"inland revenue"),
    ("stamp-duty",   r"stamp duty"),
    ("betting-gaming", r"casino|betting|gaming"),
    ("sscl",         r"social security contribution"),
    ("nbt",          r"nation building tax"),
    ("esc",          r"economic service charge"),
)


def subject(act_name: str | None, title: str = "") -> str:
    """Classify from the enabling Act, not the listing title.

    34 of the 137 listing descriptions say nothing about subject matter
    ("Notice under Paragraph 10 of Sixth Schedule"), so the Act is the signal and
    the title is only a fallback.
    """
    hay = f"{act_name or ''} {title}".lower()
    for name, pat in SUBJECTS:
        if re.search(pat, hay):
            return name
    return "other"
