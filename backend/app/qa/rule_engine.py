"""Free, no-LLM question answering: regex/keyword intent extraction over the
question text, then the exact same deterministic compute layer used by the
trend/attribution API endpoints, formatted into a Chinese-language reply.

This trades "understands any phrasing" for "costs nothing and never guesses a
number" - every value in the reply still comes straight out of compute/trends.py
and compute/attribution.py, nothing is invented. When the question is
ambiguous (department not found, or found in multiple departments), the
engine says so and lists the candidates instead of picking one silently.
"""

import re

from sqlalchemy.orm import Session

from ..compute.attribution import compute_attribution, flatten_attribution
from ..compute.trends import get_trend, list_available_months, list_departments, list_entities
from ..models import User
from ..security import get_allowed_scope, resolve_requested_filters

ENTITY_NAMES = ["PalmPay", "Flexi", "Jupiter"]

# Common Chinese business terms mapped to English words likely to appear in a
# department's official (English) name. Not exhaustive by design - if nothing
# matches, the engine falls back to whole-company scope and says so, rather
# than guessing.
CN_DEPT_KEYWORDS: dict[str, list[str]] = {
    "手机分期": ["mobile installment", "installment"],
    "分期": ["installment"],
    "信贷": ["credit"],
    "个贷": ["credit"],
    "人力资源": ["human resources"],
    "财务": ["finance"],
    "法务": ["legal"],
    "法律": ["legal"],
    "市场": ["marketing"],
    "公关": ["communication"],
    "技术": ["technology", "technical"],
    "研发": ["research and development", "research", "development"],
    "钱包": ["wallet"],
    "客服": ["customer service"],
    "合规": ["compliance"],
    "风控": ["risk"],
    "审计": ["audit"],
    "行政": ["admin"],
    "产品": ["product"],
    "线上商户": ["online merchant"],
    "线上": ["online"],
    "线下收单": ["offline acquiring"],
    "线下": ["offline"],
    "收单": ["acquiring"],
    "设计": ["design"],
    "信息安全": ["information security"],
    "合作": ["partnership"],
    "渠道": ["channels"],
    "客户资金": ["customer fund"],
    "政府关系": ["government relationships", "goverment relationships"],
    "管理层": ["management"],
    "中小企业": ["sme"],
    "平台": ["platform"],
}

ATTRIBUTION_KEYWORDS = ["为什么", "归因", "环比", "涨", "跌", "降", "增加", "减少", "上升", "下降", "变化原因", "贵", "高在哪", "低在哪"]

# Generic product terminology that shows up in almost every question and must
# never itself be read as a department reference (e.g. "人力成本" contains
# "人力", which would otherwise false-match "Human Resources").
_GENERIC_PHRASES_TO_STRIP = ["人力成本", "人力资本"]

_RANGE_RE = re.compile(r"(0?[1-9]|1[0-2])\s*[-~到至]\s*(0?[1-9]|1[0-2])\s*月")
_EXPLICIT_RE = re.compile(r"(20\d{2})[-/年](0?[1-9]|1[0-2])月?")
_BARE_RE = re.compile(r"(0?[1-9]|1[0-2])\s*月")


def _mask(text: str, span: tuple[int, int]) -> str:
    return text[: span[0]] + " " * (span[1] - span[0]) + text[span[1] :]


def _extract_months(question: str, default_year: int) -> list[str]:
    months: set[str] = set()
    text = question

    for m in list(_RANGE_RE.finditer(text)):
        start, end = int(m.group(1)), int(m.group(2))
        if start <= end:
            for mo in range(start, end + 1):
                months.add(f"{default_year:04d}-{mo:02d}")
        text = _mask(text, m.span())

    for m in list(_EXPLICIT_RE.finditer(text)):
        year, mo = int(m.group(1)), int(m.group(2))
        months.add(f"{year:04d}-{mo:02d}")
        text = _mask(text, m.span())

    for m in list(_BARE_RE.finditer(text)):
        mo = int(m.group(1))
        months.add(f"{default_year:04d}-{mo:02d}")

    return sorted(months)


def _match_department(question: str, departments: list[str]) -> tuple[str | None, list[str], bool]:
    """Returns (matched_department_or_None, ambiguous_candidates, keyword_seen_but_unmatched)."""
    q_lower = question.lower()
    candidates: set[str] = set()

    for dept in departments:
        if dept and dept.lower() in q_lower:
            candidates.add(dept)
    if candidates:
        return (next(iter(candidates)) if len(candidates) == 1 else None), sorted(candidates), False

    keyword_text = question
    for phrase in _GENERIC_PHRASES_TO_STRIP:
        keyword_text = keyword_text.replace(phrase, "")

    keyword_seen = False
    for cn_kw, en_words in CN_DEPT_KEYWORDS.items():
        if cn_kw in keyword_text:
            keyword_seen = True
            for dept in departments:
                dept_lower = dept.lower()
                if any(w in dept_lower for w in en_words):
                    candidates.add(dept)

    if len(candidates) == 1:
        return next(iter(candidates)), sorted(candidates), False
    return None, sorted(candidates), keyword_seen and not candidates


def _match_entity(question: str, entities: list[str]) -> tuple[str | None, bool]:
    """Returns (earliest_mentioned_entity_or_None, multiple_distinct_entities_mentioned)."""
    hits: list[tuple[int, str]] = []
    q_lower = question.lower()
    for entity in entities:
        if not entity:
            continue
        idx = q_lower.find(entity.lower())
        if idx != -1:
            hits.append((idx, entity))
    if not hits:
        return None, False
    hits.sort(key=lambda x: x[0])
    distinct = {e for _, e in hits}
    return hits[0][1], len(distinct) > 1


def _fmt_money(n: float) -> str:
    return f"₦{n:,.2f}"


def _scope_label(department, entity) -> str:
    def fmt(v):
        if isinstance(v, list):
            return "、".join(v) if v else None
        return v

    parts = [fmt(p) for p in (entity, department) if fmt(p)]
    return "+".join(parts) if parts else "全公司"


def _format_trend(rows: list[dict], department: str | None, entity: str | None, note: str) -> str:
    label = _scope_label(department, entity)
    if not rows:
        return f"{note}没有查到 {label} 在指定月份的数据。"

    lines = [f"{note}{label} 的人力成本趋势："]
    for r in rows:
        lines.append(f"  {r['month']}：人数 {r['headcount']}，总HR Cost {_fmt_money(r['total_hr_cost'])}，人均 {_fmt_money(r['avg_hr_cost'])}")

    if len(rows) >= 2:
        first, last = rows[0], rows[-1]
        delta = last["total_hr_cost"] - first["total_hr_cost"]
        pct = (delta / first["total_hr_cost"] * 100) if first["total_hr_cost"] else 0
        direction = "增加" if delta >= 0 else "减少"
        lines.append(
            f"从 {first['month']} 到 {last['month']}，总成本{direction}了 {_fmt_money(abs(delta))}（{pct:+.1f}%）。"
        )
    return "\n".join(lines)


def _pct_str(pct: float | None) -> str:
    return f"，约占净变化的 {pct:.1f}%" if pct is not None else ""


def _format_headcount_item(item) -> str:
    net = (item.joiners_count or 0) - (item.leavers_count or 0)
    if net > 0:
        direction = f"净增{net}人"
    elif net < 0:
        direction = f"净减{abs(net)}人"
    else:
        direction = "净变化0人"
    detail = f"新入职{item.joiners_count}人+{_fmt_money(item.joiners_cost)}，离职{item.leavers_count}人-{_fmt_money(item.leavers_cost)}"
    return f"人数变化：{direction}（{detail}），{'+' if item.amount >= 0 else ''}{_fmt_money(item.amount)}{_pct_str(item.pct)}"


def _format_line_item(item) -> str:
    if item.key == "headcount":
        return _format_headcount_item(item)
    return f"{item.label}：{'+' if item.amount >= 0 else ''}{_fmt_money(item.amount)}{_pct_str(item.pct)}"


def _format_attribution(result, department: str | None, entity: str | None, user: User, note: str) -> str:
    label = _scope_label(department, entity)
    r = result
    items = flatten_attribution(r)

    lines = [
        f"{note}{label} {r.prev_month} → {r.cur_month} 环比归因：",
        f"  {r.prev_month} 总成本 {_fmt_money(r.prev_total)}，{r.cur_month} 总成本 {_fmt_money(r.cur_total)}",
        f"  净变化：{'+' if r.net_change >= 0 else ''}{_fmt_money(r.net_change)}",
        "",
        "归因拆解（按贡献金额绝对值从大到小排序）：",
    ]
    for idx, item in enumerate(items, start=1):
        lines.append(f"  {idx}) {_format_line_item(item)}")

    lines.append("")
    items_sum = sum(i.amount for i in items)
    lines.append(
        f"校验：以上{len(items)}项相加 = {_fmt_money(items_sum)}"
        f"（{'✓ 与净变化吻合' if r.reconciled else '✗ 与净变化不吻合，数据可能有问题，此结论需要人工复核'}）"
    )

    if r.behavior_labels:
        lines.append("")
        lines.append("按变动性质分类的补充说明（一人可能同时命中多个标签，人数/金额不能跨行相加；以上面的归因拆解为准，这里仅作叙事参考）：")
        for lbl in r.behavior_labels:
            lines.append(
                f"  {lbl.label}：正式工 {lbl.count_formal} 人 + 合同工 {lbl.count_contract} 人，"
                f"涉及成本 {'+' if lbl.amount >= 0 else ''}{_fmt_money(lbl.amount)}{_pct_str(lbl.pct_of_net_change)}"
            )

    if r.anomalies:
        lines.append("")
        lines.append("⚠️ 异常信号：")
        for a in r.anomalies:
            lines.append(f"  {a}")

    if r.top_increases:
        lines.append("")
        lines.append("成本涨幅最大的几位员工：")
        for m in r.top_increases[:5]:
            name = m.name if user.role == "admin" else "[无权限查看，仅管理员可见]"
            lines.append(f"  {name}（{m.job_grade or '-'}）：+{_fmt_money(m.hr_cost)}")

    if r.leaver_reasons:
        lines.append("")
        lines.append("离职原因分布：" + "，".join(f"{k} × {v}" for k, v in r.leaver_reasons.items()))

    return "\n".join(lines)


def answer_question(db: Session, user: User, question: str) -> dict:
    available_months = list_available_months(db)
    if not available_months:
        return {"answer": "还没有任何月份的数据入库，先在“上传数据”页传一个月的发薪表并确认入库，再来问我。"}

    scope = get_allowed_scope(db, user)
    departments = list_departments(db, scope_rules=scope.rules)
    entities = list_entities(db, scope_rules=scope.rules)
    if scope.rules is not None and not scope.rules:
        return {"answer": "你的账号目前还没有被分配任何可查看的部门/实体范围，找管理员开通权限后再来问我。"}
    default_year = int(available_months[-1].split("-")[0])

    department, dept_candidates, dept_keyword_unmatched = _match_department(question, departments)
    entity, multiple_entities = _match_entity(question, entities)
    months = [m for m in _extract_months(question, default_year) if m]

    note = ""
    if len(dept_candidates) > 1:
        return {
            "answer": f"你说的部门有点模糊，匹配到了好几个可能：{', '.join(dept_candidates)}。麻烦换一个更具体的部门名称再问一次。"
        }
    if dept_candidates and not department:
        department = dept_candidates[0]
    if dept_keyword_unmatched:
        note += "（问题里像是提到了某个部门，但没能匹配到现有部门，已按你的权限范围统计；可以试试直接用部门的英文名）"
    if multiple_entities:
        note += f"（识别到多个实体，暂不支持一次对比多个，本次只按最先提到的 {entity} 统计，如需对比请分开问）"

    department, entity = resolve_requested_filters(scope, department, entity)

    unavailable = [m for m in months if m not in available_months]
    months = [m for m in months if m in available_months]
    if unavailable:
        note += f"（注意：{', '.join(unavailable)} 还没有数据，已忽略）"

    is_attribution_question = any(kw in question for kw in ATTRIBUTION_KEYWORDS)

    if is_attribution_question and len(months) >= 2:
        prev_month, cur_month = min(months), max(months)
        if len(months) > 2:
            note += f"（识别到多个月份，已取最早的 {prev_month} 和最晚的 {cur_month} 做归因对比）"
        result = compute_attribution(db, prev_month, cur_month, department=department, entity=entity, scope_rules=scope.rules)
        return {"answer": _format_attribution(result, department, entity, user, note)}

    if is_attribution_question and len(months) < 2:
        return {
            "answer": f"{note}归因分析需要指定两个月份做对比（比如“{department or 'XX部门'}6月为什么比5月成本高”），麻烦补充清楚再问一次。"
        }

    if not months:
        months = available_months
        note += f"（没有指定月份，默认展示 {available_months[0]} 到 {available_months[-1]} 全部已入库月份）"

    rows = get_trend(db, months=sorted(months), department=department, entity=entity, scope_rules=scope.rules)
    return {"answer": _format_trend(rows, department, entity, note)}
