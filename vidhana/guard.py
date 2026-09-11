"""Refuse to publish a corpus that got smaller.

The nightly job rebuilds everything from scratch and commits whatever comes
out. On 2026-09-10 what came out was seven gazettes short, with seven
summaries deleted, and the commit said "0 new in the last 30 days". Nothing
was wrong with any single step — each did what it was asked on the input it
had — so no per-step check would have caught it. What would have is noticing
that the output shrank.

So this compares what a run is about to commit against what is already
committed, and fails if anything would disappear. It is deliberately ignorant
of *why*: a document the rebuild could not re-acquire, a gazette the IRD
quietly delisted, a parser change that stops recognising a file — all of
these look the same from here, and all of them want a human before they go
out. The corpus is append-only as far as anyone knows (PHASE0.md §7), so a
shrink is never routine.

Growth is not checked. A new gazette is the whole point of the job.
"""
from __future__ import annotations

import json
import subprocess

# What the nightly job commits, and the identity of each record in it.
TRACKED = {
    "gazettes": ("docs/data/index.json", lambda d: [g["no"] for g in d["gazettes"]]),
    "summaries": ("data/summaries.json", lambda d: [r["no"] for r in d]),
}


def shrinkage(before: dict[str, set[str]], after: dict[str, set[str]]) -> dict[str, list[str]]:
    """Records present before and absent after, per kind. Empty means safe."""
    lost = {k: sorted(before.get(k, set()) - after.get(k, set())) for k in before}
    return {k: v for k, v in lost.items() if v}


def _load(text: str | None, pick) -> set[str]:
    return set(pick(json.loads(text))) if text else set()


def committed(rev: str = "HEAD") -> dict[str, set[str]]:
    """The tracked artefacts as of a git revision. A file that does not exist
    there yet is an empty baseline, not an error — a first run shrinks nothing."""
    out = {}
    for kind, (path, pick) in TRACKED.items():
        r = subprocess.run(["git", "show", f"{rev}:{path}"], capture_output=True, text=True)
        out[kind] = _load(r.stdout if r.returncode == 0 else None, pick)
    return out


def working() -> dict[str, set[str]]:
    """The tracked artefacts as this run wrote them."""
    out = {}
    for kind, (path, pick) in TRACKED.items():
        try:
            with open(path) as f:
                out[kind] = _load(f.read(), pick)
        except FileNotFoundError:
            out[kind] = set()
    return out
