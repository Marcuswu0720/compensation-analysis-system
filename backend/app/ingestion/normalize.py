"""DB-backed canonical name resolution for department / entity labels.

Handles PRD 坑4: the same department/entity shows up with inconsistent
casing across (and sometimes within) a single month's file. The canonical
display form for a given lowercased key prefers a "properly capitalized"
form (every word starts with an uppercase letter) over a miscapitalized one
even if the miscapitalized one is more common in the raw export - ties (or
no properly-capitalized candidate) fall back to whichever exact form has
been seen most often. This matches both observed real cases: "Mobile
Installment Business" (10 rows) should win over the far more common but
miscapitalized "Mobile installment Business" (10k+ rows), while "PalmPay"
vs "Palmpay" - both properly-capitalized - correctly resolves by frequency.

Resolution happens in two passes per upload (see `prepare`): first every raw
label from the whole workbook is tallied and canonical forms are finalized,
then `resolve` just looks values up. Two passes matter because doing it in
one pass could let the canonical flip mid-file, so earlier rows in the same
upload would end up tagged with a different display string than later rows.
"""

import json
from collections import Counter

from sqlalchemy.orm import Session

from ..models import CanonicalName
from .constants import ENTITY_ALIASES

DEFAULT_DEPARTMENT = "(未标注部门)"
DEFAULT_ENTITY = "(未标注实体)"


def _is_properly_capitalized(s: str) -> bool:
    return all(w[:1].isupper() for w in s.split() if w)


def _pick_canonical(counts: Counter) -> str:
    proper_forms = [f for f in counts if _is_properly_capitalized(f)]
    candidates = proper_forms or list(counts.keys())
    return max(candidates, key=lambda f: counts[f])


class NameResolver:
    def __init__(self, db: Session, month: str):
        self.db = db
        self.month = month
        self.variant_issues: list[dict] = []
        self._cache: dict[tuple[str, str], str] = {}

    def prepare(self, category: str, raw_values: list) -> None:
        per_lower: dict[str, Counter] = {}
        for raw in raw_values:
            if not raw or not str(raw).strip():
                continue
            raw = str(raw).strip()
            if category == "entity" and raw.lower() in ENTITY_ALIASES:
                raw = ENTITY_ALIASES[raw.lower()]
            per_lower.setdefault(raw.lower(), Counter())[raw] += 1

        for lower, counter in per_lower.items():
            record = (
                self.db.query(CanonicalName)
                .filter(CanonicalName.category == category, CanonicalName.raw_lower == lower)
                .first()
            )
            existing_counts = json.loads(record.seen_raw_forms_json) if record else {}
            new_forms = [f for f in counter if f not in existing_counts]

            merged = Counter(existing_counts)
            merged.update(counter)
            new_canonical = _pick_canonical(merged)

            if record is None:
                if len(counter) > 1:
                    minority = [f for f in counter if f != new_canonical]
                    self.variant_issues.append(
                        {
                            "issue_type": "dept_name_variant" if category == "department" else "entity_name_variant",
                            "issue_detail": (
                                f'"{lower}" 首次出现即存在多种写法 {list(counter.keys())}，'
                                f'已按出现次数最多的 "{new_canonical}" 作为标准名，其余写法 {minority} 已归并统计'
                            ),
                            "row_count_affected": sum(counter[f] for f in minority),
                        }
                    )
                record = CanonicalName(
                    category=category,
                    raw_lower=lower,
                    canonical_display=new_canonical,
                    first_seen_month=self.month,
                    seen_raw_forms_json=json.dumps(dict(merged)),
                )
                self.db.add(record)
            else:
                old_canonical = record.canonical_display
                if new_forms:
                    for f in new_forms:
                        self.variant_issues.append(
                            {
                                "issue_type": "dept_name_variant" if category == "department" else "entity_name_variant",
                                "issue_detail": f'"{old_canonical}" 出现新写法: "{f}"，已归并统计',
                                "row_count_affected": counter[f],
                            }
                        )
                record.seen_raw_forms_json = json.dumps(dict(merged))
                record.canonical_display = new_canonical
            self.db.flush()
            self._cache[(category, lower)] = record.canonical_display

    def resolve(self, category: str, raw) -> str:
        if not raw or not str(raw).strip():
            return DEFAULT_DEPARTMENT if category == "department" else DEFAULT_ENTITY
        raw = str(raw).strip()
        if category == "entity" and raw.lower() in ENTITY_ALIASES:
            raw = ENTITY_ALIASES[raw.lower()]
        return self._cache.get((category, raw.lower()), raw)

    def flush_issues(self) -> list[dict]:
        return self.variant_issues
