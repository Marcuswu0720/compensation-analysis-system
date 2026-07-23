"""Tool (function-calling) definitions exposed to Claude for the Q&A layer.

Claude never sees raw payroll rows. It can only call these two tools, whose
results come straight out of the deterministic compute layer (compute/trends.py,
compute/attribution.py). This is the mechanism behind the PRD's core design
rule: "计算层的归因逻辑必须是可复现的确定性代码...大模型只负责组织语言".
"""

TOOLS = [
    {
        "name": "get_cost_trend",
        "description": (
            "查询指定部门/实体在一段月份范围内，每月的在职人数、总HR Cost（人力成本）、人均HR Cost。"
            "department 和 entity 都不填时返回全公司口径。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "description": "标准化后的部门名称，必须从提供的部门列表中选择，不确定就留空"},
                "entity": {"type": "string", "description": "法律实体，如 PalmPay / Flexi / Jupiter，不确定就留空"},
                "start_month": {"type": "string", "description": "起始月份，格式 YYYY-MM"},
                "end_month": {"type": "string", "description": "结束月份，格式 YYYY-MM"},
            },
        },
    },
    {
        "name": "get_attribution",
        "description": (
            "对比两个相邻或指定的月份，拆解某部门/实体人力成本变化的原因："
            "新入职带来的成本、离职减少的成本、留任员工的成本变化，以及三项相加与净变化的校验。"
            "还会返回留任员工里成本涨幅/降幅最大的几位（如果当前用户权限允许查看姓名）。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "department": {"type": "string", "description": "标准化后的部门名称，不填则为全公司口径"},
                "entity": {"type": "string", "description": "法律实体，不填则不限"},
                "prev_month": {"type": "string", "description": "对比的前一个月份，格式 YYYY-MM"},
                "cur_month": {"type": "string", "description": "对比的当前月份，格式 YYYY-MM"},
            },
            "required": ["prev_month", "cur_month"],
        },
    },
]
