"""Normalized, whitespace/case-tolerant header matching (PRD V1.8 §1).

Root-cause fix for a bug class that had already recurred 5+ times by V1.8:
a target field ends up empty in an export because the real file spells its
header slightly differently than the hand-maintained alias list expects
(`Staff Name` vs `Staff name`, `Joining Date` vs `Joining date`, a stray
trailing space on `Exit Date `). The old mechanism matched aliases against
raw headers with exact string equality, so every new casing/whitespace
variant needed a human to notice the gap and add one more alias - a
"打地鼠" loop that can never fully catch up with next month's file.

Splitting matching into two layers fixes this without ever needing a
complete alias list:
  1. Normalization (this module): strip + collapse internal whitespace +
     lowercase, applied to BOTH the raw header and every alias before
     comparing. Catches `Staff Name` / `Staff name` / `  Staff Name  `
     automatically - no alias-list change ever needed for this class of
     drift again.
  2. Synonym aliases (still hand-maintained, e.g. in full_fields.py /
     constants.py): only for genuinely different wording (`Resign Date` vs
     `Leaving date`), which no amount of normalization can bridge - this is
     the much shorter list PRD V1.8 §1.2 describes.
"""

import re


def normalize_header(value) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).lower()


def build_header_index(headers) -> dict[str, str]:
    """normalized header text -> the first raw header text seen for it."""
    index: dict[str, str] = {}
    for h in headers:
        norm = normalize_header(h)
        if norm and norm not in index:
            index[norm] = h
    return index


def find_alias(index: dict[str, str], aliases) -> str | None:
    """First alias (checked in declaration order) that matches some header
    in `index`, returning the ORIGINAL raw header text as it appeared in the
    file - so callers can still look values up from a row dict keyed by raw
    headers, exactly as before this module existed."""
    for alias in aliases:
        raw = index.get(normalize_header(alias))
        if raw is not None:
            return raw
    return None
