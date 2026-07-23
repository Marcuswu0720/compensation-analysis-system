"""Drives the Claude tool-use loop: Claude picks a tool + args, we run the
deterministic compute layer, feed the JSON result back, repeat until Claude
produces a final natural-language answer. Claude never receives raw employee
rows — only the aggregated/attributed numbers the compute layer returns.
"""

import json
from dataclasses import asdict

from sqlalchemy.orm import Session

from ..config import settings
from ..compute.attribution import compute_attribution
from ..compute.trends import get_trend, list_departments, list_entities, list_available_months
from ..models import User
from .claude_client import get_client
from .tools import TOOLS

SYSTEM_PROMPT_TEMPLATE = """你是尼日利亚薪酬人力成本分析工具里的问答助手，服务对象是公司内部HR/管理层。

规则（必须严格遵守）：
1. 你自己不知道任何具体的人力成本数字，所有数字必须通过调用工具获取，绝不能凭猜测或记忆编造数字。
2. 部门名称必须从下面提供的"有效部门列表"里选一个最匹配的传给工具；如果用户说的部门在列表里找不到接近的匹配，不要瞎猜，直接在回复里说明找不到该部门，并列出几个相近的选项让用户确认。
3. 月份必须是下面"有效月份列表"里存在的月份，格式 YYYY-MM；如果用户说"这个月"、"上个月"等相对说法，且无法确定具体对应哪个月，先询问澄清。
4. 环比归因类问题（"为什么涨了/为什么降了"）必须调用 get_attribution，不要只调用 get_cost_trend 就下结论。
5. 回答要用人话组织，但每个关键数字都要能对应工具返回的结果；如果工具返回 reconciled=false（三项相加对不上净变化），必须在回答里明确提示"数据校验异常，此结论需要人工复核"，不要假装没看到。
6. 如果留任员工的姓名被标记为"[无权限查看，仅管理员可见]"，不要编造姓名，直接原样说明看不到明细姓名。

有效部门列表: {departments}
有效实体列表: {entities}
有效月份列表: {months}
"""


def _redact_if_needed(result: dict, user: User) -> dict:
    if user.role == "admin":
        return result
    for key in ("top_increases", "top_decreases"):
        for item in result.get(key, []):
            item["name"] = "[无权限查看，仅管理员可见]"
            item["staff_id"] = "[隐藏]"
    return result


def _execute_tool(db: Session, user: User, name: str, tool_input: dict) -> dict:
    if name == "get_cost_trend":
        months = None
        if tool_input.get("start_month") and tool_input.get("end_month"):
            available = list_available_months(db)
            months = [m for m in available if tool_input["start_month"] <= m <= tool_input["end_month"]]
        trend = get_trend(
            db,
            months=months,
            department=tool_input.get("department") or None,
            entity=tool_input.get("entity") or None,
        )
        return {"trend": trend}

    if name == "get_attribution":
        result = compute_attribution(
            db,
            prev_month=tool_input["prev_month"],
            cur_month=tool_input["cur_month"],
            department=tool_input.get("department") or None,
            entity=tool_input.get("entity") or None,
        )
        result_dict = asdict(result)
        return _redact_if_needed(result_dict, user)

    return {"error": f"未知工具: {name}"}


def answer_question(db: Session, user: User, question: str) -> dict:
    client = get_client()
    departments = list_departments(db)
    entities = list_entities(db)
    months = list_available_months(db)

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
        departments=", ".join(departments) or "(暂无数据)",
        entities=", ".join(entities) or "(暂无数据)",
        months=", ".join(months) or "(暂无数据)",
    )

    messages = [{"role": "user", "content": question}]
    tool_calls_log = []

    for _ in range(6):  # hard cap so a confused model can't loop forever
        response = client.messages.create(
            model=settings.anthropic_model,
            max_tokens=1500,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

        if response.stop_reason != "tool_use":
            final_text = "".join(block.text for block in response.content if block.type == "text")
            return {"answer": final_text, "tool_calls": tool_calls_log}

        messages.append({"role": "assistant", "content": response.content})
        tool_results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            result = _execute_tool(db, user, block.name, block.input)
            tool_calls_log.append({"tool": block.name, "input": block.input, "result": result})
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result, ensure_ascii=False, default=str),
                }
            )
        messages.append({"role": "user", "content": tool_results})

    return {"answer": "抱歉，这个问题拆解得有点复杂，我暂时没能给出确定的回答，请尝试拆分成更具体的问题。", "tool_calls": tool_calls_log}
