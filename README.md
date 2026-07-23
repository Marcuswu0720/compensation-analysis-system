# 尼日利亚薪酬人力成本分析工具

内部管理工具：上传月度原始发薪表 Excel，自动解析清洗校验，支持部门/实体成本趋势查询、
月度环比归因分析，以及基于 Claude API 的自然语言问答。技术方案见 `PRD.md`（如未包含，参见项目内文档）。

设计原则：**计算层是确定性代码，模型只负责把算好的数字组织成人话**。所有问答类回答都来自
`backend/app/compute/` 里的部门/实体成本聚合和环比归因函数，Claude 通过 tool use 调用这些函数，
从不直接读取原始数据自己编数字。

## 目录结构

```
backend/
  app/
    ingestion/     # 解析：sheet 匹配、字段别名映射、汇总行过滤、部门/实体名称标准化
    compute/       # 计算：趋势聚合、环比归因（joiners/leavers/stayers + 校验）
    qa/            # 问答：Claude tool-use 编排
    routers/       # FastAPI 路由：auth / upload / query / chat
    models.py      # 数据表结构
    main.py        # 应用入口
  seed_admin.py    # 创建/重置管理员账号
  tests/           # 用合成数据（非真实薪酬数据）跑的回归测试
frontend/          # 纯静态页面：登录 / 上传+校验+图表+问答（无需构建步骤）
```

## 本地运行

```bash
cd backend
pip install -r requirements.txt

# 配置密钥（问答功能需要 ANTHROPIC_API_KEY，登录功能需要 SECRET_KEY）
cp ../.env.example ../.env
# 编辑 .env 填入真实值

# 创建第一个管理员账号
python seed_admin.py marcus <你的密码>

# 启动
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

浏览器打开 `http://localhost:8000` 登录。管理员可在"上传数据"页新建其他账号（当前需通过
`POST /api/auth/users` 接口，携带 `role: admin | viewer`；viewer 角色看不到员工姓名/工号明细，
只能看到部门/实体汇总层级的数字）。

## 使用流程

1. **上传**：选择月份 + 原始发薪表 Excel，系统自动解析并展示校验摘要（人数、成本、发现的问题：
   部门/实体名称新写法、汇总行过滤、缺失字段、未识别的 sheet 等）。
2. **确认入库**：核对无误后点击确认，数据才正式写入统计表；点"放弃"则本次上传作废，不影响已有数据。
   同一个月份重新上传并确认，会整体覆盖该月旧数据。
3. **趋势查询**：按部门/实体/月份范围查看人数、总 HR Cost、人均 HR Cost 趋势图。
4. **环比归因**：选两个月份对比，拆解新入职/离职/留任三项对成本变化的贡献，并列出留任员工里涨跌幅最大的几位（仅管理员可见姓名）。
5. **问答**：用自然语言提问，例如"手机分期部门1-6月人力成本怎么变化的"、"XX部门6月为什么比5月成本高"。

## 已知限制（对齐 PRD MVP 范围）

- 权责发生制下奖金按业绩归属月拼接的完整口径（月度快照已记录 `monthly_bonus_snapshot`，
  但趋势/归因计算目前用的是现金流口径的 `HR Cost`，与 PRD 验证的基准数字一致）。
- 跨部门转岗员工的历史轨迹追溯、薪酬 benchmark 联动、异常自动预警：留到后续版本。
- 上传文件中出现的、当前规则识别不了的新 sheet（例如一次性的补发工资表）会被标记为
  "未识别的sheet"且不计入统计，需要人工判断是否要在 `backend/app/ingestion/constants.py`
  里补充匹配规则。

## 测试

```bash
cd backend
python -m pytest tests/ -v
```

测试用的是合成数据（`tests/xlsx_fixtures.py` 现造的假工作簿），不包含任何真实员工信息，
覆盖 sheet 命名漂移、字段别名漂移、部门名大小写归并、汇总行过滤、月中离职仍计入当月成本、
归因三项校验等 PRD 里列出的坑。真实数据的端到端验证已经在开发过程中人工跑通，数字与 PRD
第六章的基准完全一致，但真实薪酬文件不会被提交到仓库。
