"""Phase 3: search across the corpus, answering with resolved state.

The point of this module is the difference between two questions:

    "which documents mention the tax invoice format?"      — plain full-text
    "what is the rule on tax invoice formats right now?"   — what a reader wants

Everything here is deterministic. The resolver (`resolve.py`) already knows
which documents are in force; search's job is to carry that state into the
result rather than returning a list of PDFs and leaving the reader to work out
which of them still stands. No LLM runs at query time.

Facets are derived, not stored as the model wrote them. Measured over the
corpus: 225 of 319 distinct tags are used exactly once and 95 of 105 audience
strings are unique, so the model's own strings describe a document well and
navigate it badly. Tags are folded to a key and given a display form; audience
is grounded back to the enabling Act's candidate list.
"""
from __future__ import annotations

import collections

from .structure import audience_candidates

# True synonyms only. Mechanical plural folding (below) already merges
# tax-rate/tax-rates and tax-exemption/tax-exemptions, so this map is for pairs
# no rule can catch: an abbreviation, a differently-inflected stem, two names
# for one thing. Kept deliberately short — over-merging tags destroys the
# distinctions the model got right.
TAG_ALIAS = {
    "vat": "value-added-tax",
    "debit-tax": "debits-tax",
    "excise": "excise-tax",
    "withholding": "withholding-tax",
    "tax-invoicing": "tax-invoices",
    "importation": "imports",
    "casino-regulation": "casino-licensing",
    "port-city": "colombo-port-city",
    "svat-transition": "svat",
    "amendment": "gazette-amendment",
    "gazette-correction": "gazette-amendment",
    "freight-forwarding": "freight-forwarders",
}


def _depluralise(word: str) -> str:
    """Fold an English plural to its stem. Only ever applied to the final token
    of a tag, where the head noun sits: `tax-rates` -> `tax-rate`, but
    `debits-tax` is left alone because its plural is not at the end."""
    if len(word) < 4 or word.endswith("ss"):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def tag_key(raw: str) -> str:
    """Fold a model-written tag to a canonical key.

    The key is for grouping, not display — `notaries` and `notary` both key to
    `notary`, which reads oddly in a facet list. `canonical_tags` picks the form
    a human sees.
    """
    t = "-".join(raw.strip().lower().split())
    t = t.strip("-")
    t = TAG_ALIAS.get(t, t)
    if not t:
        return ""
    parts = t.split("-")
    parts[-1] = _depluralise(parts[-1])
    key = "-".join(parts)
    return TAG_ALIAS.get(key, key)


def canonical_tags(raws: list[str]) -> dict[str, str]:
    """key -> the display form for that key, over a whole corpus of raw tags.

    The winner is the most-used raw variant, ties broken alphabetically so the
    result does not depend on row order. This is why facets are rebuilt
    wholesale rather than per document: the display form is a corpus-level fact.
    """
    groups: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for raw in raws:
        key = tag_key(raw)
        if key:
            groups[key]["-".join(raw.strip().lower().split())] += 1
    return {key: min(c.items(), key=lambda kv: (-kv[1], kv[0]))[0] for key, c in groups.items()}


def _words(s: str) -> list[str]:
    return [w for w in "".join(c if c.isalnum() else " " for c in s.lower()).split()]


def ground_audience(act: str | None, audience: str, subject: str | None = None):
    """Match one model-written audience string back to its Act's candidate list.

    CLAUDE.md: the audience is not in the documents. It is inferred from the
    enabling Act, and the model may only narrow within the Act's candidates,
    never invent one. This is where that rule is checked rather than merely
    asked for.

    Returns `(coarse, reason)`. Three outcomes, and they mean different things:

        ("VAT-registered businesses", "grounded")  narrowed within the map
        (None, "no-map")                           the Act has no map to obey
        (None, "ungrounded")                       it had a map and left it

    Only the third is a finding about the model. Collapsing the first two into
    "not grounded" would report a gap in our curation as a model failure.
    """
    candidates = audience_candidates((act or "").replace("The ", ""), subject)
    if not candidates:
        return None, "no-map"
    if not audience:
        return None, "ungrounded"
    got = {_depluralise(w) for w in _words(audience)}
    best, best_hit, best_score = None, 0, 0.0
    for cand in candidates:
        want = [_depluralise(w) for w in _words(cand) if len(w) > 3]
        if not want:
            continue
        hit = sum(w in got for w in want)
        score = hit / len(want)
        if (hit, score) > (best_hit, best_score):
            best, best_hit, best_score = cand, hit, score
    # Two ways to ground, because the candidates are not the same shape. Short
    # ones are noun phrases and want a ratio: "VAT-registered wholesalers and
    # retailers" keeps one word of two from "VAT-registered businesses" and is
    # plainly a narrowing. Long ones enumerate — "parties to leases, transfers
    # and other stampable instruments" — and a narrowing keeps one branch of the
    # list and drops the rest, so demanding half the words would reject exactly
    # the documents that obeyed the instruction. Two distinctive words is the
    # floor for those.
    if best_score >= 0.5 or best_hit >= 2:
        return best, "grounded"
    return None, "ungrounded"
