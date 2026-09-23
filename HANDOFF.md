# HANDOFF

这份文档是给接手这个项目的人（人或未来的 Claude 会话）看的交接材料，汇总本项目从 0 到当前
状态的关键决策、已完成的改动、技术选型、未完成事项和已知的坑。业务/操作层面的说明（怎么上传、
怎么看报表）请看 `README.md`；这份文档只讲"为什么这么做"和"接下来要注意什么"。

## 项目是什么

给 PalmPay 尼日利亚做的内部薪酬/人力成本分析工具。使用者是非技术背景的 Marcus，驱动方式是他
持续上传 PRD（`PRD_V1.x.md`），每次说"请迭代"，助手读 PRD、对照代码库、实现、写测试、更新文档、
提交推送。技术栈刻意选得很轻：FastAPI + SQLAlchemy + SQLite 后端，原生 JS 前端（Chart.js 画图，
不用任何构建工具/框架），itsdangerous 做 cookie session，bcrypt 做密码哈希。SQLite 迁移是手写的
（`migrations.py`，没用 Alembic）。

## 核心架构决策（贯穿始终，改动前务必先理解）

1. **计算层是确定性代码，回答只是把算好的数字套进句子模板**——这句话在整个项目里被反复强调。
   `compute/` 目录下的函数是唯一的数字来源，问答模块（`qa/rule_engine.py`，纯关键词匹配，不接
   任何大模型）和网页看板必须消费同一套后端计算结果，绝不允许任何一层自己重新算一遍或者让 LLM
   现算数字。
2. **"计算逻辑只写一套，不要为每个新需求另起一套并行实现"**——这条原则从 V1.7 开始被反复应用：
   V1.7 把"环比归因"泛化成任意两月对比后，直接让"趋势查询"页面的"两点比较"模式复用同一个接口，
   而不是新写一套；V1.9 给"薪资类目"页面加人均/中位数/用工类型拆分时，做法是给已有的
   `compute/categories.py::get_categories_trend()` 加两个可选参数（`per_capita`、
   `employment_type`），"正式工 vs 合同工对比"在后端完全不是一个新模式，就是拿同一个函数用不同
   参数调用两次，前端合并展示。以后新需求如果看起来像是"给某个页面加个新维度"，先检查能不能通过
   给现有聚合函数加可选参数来实现，而不是新建一套。
3. **迁移只加列，不删列**——SQLite 删列需要重建整张表，代价和风险都不小，所以约定是：淘汰的字段
   保留在表里但不再写入（比如 V1.8 之后 `cost_center`/`work_country`/`state`/`work_station`
   这几个 V1.6 时代猜的字段名已经废弃，但列还在）。新迁移只用 `ALTER TABLE ... ADD COLUMN`，
   加之前检查 `if column not in existing_columns`，在 `Base.metadata.create_all()` 之后、
   应用启动时跑（见 `migrations.py`）。
4. **"在职人数"统一用现金流口径（含当月内离职）**——`get_trend()`、`compute_attribution()`、
   V1.9 的人均分母，三处口径完全一致：只要这个月内发过薪就算在职人数里，不区分月初/月末在职。
   这个口径是跟 Marcus 明确确认过的产品决策，不要在某个新功能里自己发明一个不一样的定义。
5. **权限模型**：`ViewerPermission` 表存"实体+部门"级别的授权规则（`scope_type` 为 `entity` 或
   `entity_department`），`compute/scope.py` 的 `apply_scope_filter`/`apply_permission_scope`
   是唯一允许做权限过滤的地方——V1.2 的教训是绝不能让某个新查询自己拼一个"按部门名字符串过滤"
   的逻辑，因为不同实体下可能存在同名部门（比如两个不同实体下都有"Ops"部门），字符串匹配会导致
   越权。下载明细（`compute/export.py`）复用的是同一套权限原语，不是单独实现的。
6. **字段名匹配：两层机制**（V1.8 建立，是这个项目里出现频率最高的一类 bug 的根本修复）：
   - 第一层，**归一化匹配**（`ingestion/header_match.py`）：去首尾空格、压缩多余空格、转小写后
     比较，解决"Staff Name"/"Staff name"/" Staff Name "这种大小写和空白差异，不需要为每种写法
     单独维护别名。
   - 第二层，**同义词别名列表**：只用于真正换了个词的情况（比如"Resign Date" vs "Leaving
     date"），列在 `ingestion/full_fields.py` 各个 `FieldSpec` 的 `source_aliases` 元组里，
     多个别名按顺序尝试。
   - 这套机制统一应用在四个地方：核心字段解析（`parser.py`）、完整字段清单解析
     （`full_fields.py`）、奖金批次解析（`bonus_batch.py`）、薪资类目字段解析
     （`salary_components.py`）——新增任何字段解析逻辑都必须走这套机制，不能退回到精确字符串
     匹配。
7. **上传阶段的字段匹配诊断**（V1.8）：每次上传，`check_field_mapping()` 会检查当前 sheet 的
   表头覆盖了多少目标字段，缺了哪些、试过哪些别名，作为校验摘要的一部分展示给用户，而不是等到
   导出 Excel 才发现某个字段是空的。

## 迭代历史（按提交顺序，只列关键决策，细节看对应 commit message）

- **V1.1 及更早**（初始搭建 + V1.1）：搭建 FastAPI+SQLite 后端、登录/权限、上传+校验+图表+
  问答前端；后来把问答从"接 Claude API"换成免费的关键词/正则规则引擎（`qa/rule_engine.py`），
  因为这是内部工具，不值得为问答单独付费用大模型 API，而且计算层已经是确定性的，问答只是模板化
  输出。V1.1 加了薪资类目拆分、部门级只读权限。
- **V1.2**：权限模型重构成"实体+部门"规则表，支持账号禁用和密码重置，支持一次操作里给多个
  实体/部门授权。
- **V1.3**：员工级薪酬明细 Excel 导出，带下载权限过滤、审计日志、水印。
- **V1.5**：归因分析文案从"嵌套结构"改成"扁平化列表"展示（更符合非技术用户的阅读习惯）；
  上传校验环节加了分部门×分薪资类目的核对导出；下载功能加批次类型筛选。
- **V1.6**：这是一次数据模型的大扩展——之前只解析、只存了约 10 个"分析用"字段（底薪/绩效/奖金/
  加班/其他收入等），部门二级/三级、职位、汇报线、州、工作站点、考勤扣款明细等原始表里有的字段
  从解析那一步就被丢弃了。V1.6 建了完整字段清单框架（`ingestion/full_fields.py`）、把
  Formal/Contract 扩到 37/29 个字段、奖金批次重写成结构化的 26 字段解析器、导出层加了字段数量
  自检（导出前检查列数是否等于期望值，防止"少了 20 列却没人发现"再次发生）。**但这次新增的约
  50 个字段的原始列名，除了早前验证过的约 10 个"分析用"字段，其余全是根据 PRD 文字描述猜的，
  没有拿真实文件核对过**——这个"猜的"欠账后来在 V1.8 和 V1.9 之后的热修复里逐步还清。
- **V1.7**：把"环比归因"泛化成支持任意两个月份对比（不再要求相邻），统一进"趋势查询"页面的
  "两点比较"模式；"薪资类目"页面从单选改成多选，加了趋势/两点比较两种模式和绝对金额/增长百分比
  两种视图。
- **两次 bug 修复**（V1.7 和 V1.8 之间，都是用户上传真实文件后报的）：
  1. openpyxl 对日期格式的单元格会返回真正的 `datetime.datetime` 对象，V1.6 的 JSON 序列化
     没有处理全部情况，导致真实一月文件上传时报"Object of type datetime is not JSON
     serializable"。
  2. 用户上传奖金文件后显示 0 人头——诊断出来是用户在"薪酬类型"下拉框里选错成了"底薪批次"，
     不是代码 bug，但同时提醒了"奖金批次的字段名全是 V1.6 猜的，从没验证过"这个隐患。
- **V1.8**：一次根本性修复，处理了三类问题（全部由"姓名缺失"这个真实生产 bug 触发）：
  1. 字段匹配逻辑本身的问题——精确字符串匹配 → 上面说的两层机制。
  2. 字段映射内容的问题——用户提供了权威的"数据导出展示字段-映射.xlsx"，据此重建了
     `full_fields.py` 里的三份字段清单（正式工 **40**、合同工 **33**、奖金批次 **24**，全部
     标记为 `verified=True`），并且修正了一个真正的错误假设：合同工的雇主侧社保成本以前是自己
     把 NSITF+Pension ER+ITF+HMO 四列加总算出来的，映射文件显示合同工表其实有现成的
     `ER COST` 列，直接读就行。
  3. 日期格式修复——统一在解析入库那一步格式化成纯 `YYYY-MM-DD` 字符串（`ingestion/
     date_utils.py` 的 `format_date_value()`），不再是带时间的 ISO 格式。
  - 顺带修了一个手工测试时发现的真 bug：`if not sheet_result: continue` 是死代码（
    `parse_workbook()` 对每个角色都返回非 `None` 的对象），导致对根本不存在的 sheet 也报出
    "字段匹配诊断"的误导性警告。
- **V1.9**：给"薪资类目"页面加了**统计口径**（总额/人均）和**用工类型**（全部/仅正式工/仅
  合同工/正式工 vs 合同工对比）两个维度，按上面"只写一套逻辑"的原则扩展了
  `get_categories_trend()`。人均模式下同时给均值和中位数是因为 SQLite 没有可移植的
  `MEDIAN()`，走的是取原始逐人数据后用 Python `statistics.median` 计算的独立代码路径（非
  人均模式还是原来高效的 SQL `SUM` 分组查询，没有改动）。开发时用一个刻意构造的数据集验证了
  这个功能真正要防的场景：合并口径的人均在下降，但正式工和合同工各自的人均都在上升（辛普森
  悖论——低薪的合同工占比上升拉低了整体均值）。
- **V1.9 之后的热修复**（这次会话的最新一轮，用户直接反馈 + 提供了两份真实一月份文件）：
  1. **中位数默认展示改成可选**——V1.9 的 PRD 原话要求"均值和中位数必须同时可见，不能只做成
     需要额外点击才能看到的隐藏信息"，但用户后来明确要求反过来："需要有一个选项，不要默认有
     中位数"。已经改成一个默认不勾选的"同时显示中位数"复选框，只在人均口径下出现。**这是一次
     用户明确覆盖此前 PRD 决策的例子，说明"PRD 里写的要求"不是一成不变的，最新的用户指令优先。**
  2. **用真实文件验证发现的字段映射 bug**——Contract-Flexi sheet 的表头跟 Contract-PP 不是
     同一套写法（`Position` vs `Job Title`、`Chinese Reporting line` vs `Reporting Line`、
     `Work Location` vs `Work Station`、`Should Working Days` vs `Working Days`、外加一个
     话补列多了后缀文字），之前只认 PP 的写法，这几个字段在 Flexi 行里全是空的；奖金批次真实
     表头是 `Staff Type`/`Position`/`Line Manager`，不是映射文件写的
     `Employment Type`/`Job Title`/`Reporting Line`。都已按第二条别名的方式修复，并补了用
     真实表头结构写的回归测试（不是编的假数据）。
  3. **日期显示的"二次防御"**——发现问题的根源分两种：如果某行数据是**在 V1.8 日期修复之前**
     confirm 入库的，数据库里已经存了一个诸如 `"2026-01-04 00:00:00"` 的普通字符串（不再是
     真正的 `datetime` 对象），`format_date_value()` 认不出这种已经字符串化的旧数据。新增了
     `format_date_for_display()`，在导出/读取时做二次格式化，**不需要重新上传旧数据**就能让
     导出文件里的日期显示正确。但如果是"迟到扣款/未满月天数"这类字段在旧版本入库时压根没被
     解析出来（不是格式问题，是当时的字段别名就没匹配上），那部分数据没法靠读时修复找回，只能
     删除重新上传那个月的批次——这两种坑的区别（"格式问题可以补救" vs "从没抓到值必须重新
     上传"）以后遇到类似"老数据显示不对"的反馈时要先分清楚是哪一种。
- **V1.9 热修复之后的第二轮**（本次会话，起点是用户用真实一月导出文件复核后反馈"扣款金额依旧
  丢失"+"奖金基础信息依旧丢失"，过程中用户又陆续用真实文件/真实操作反馈了另外几个问题，全部在
  同一轮会话里处理。九项：① 正式工/合同工扣款金额字段别名猜错 ② 奖金批次基础信息缺兜底
  ③ Contract 的 basic_salary_actual 诊断误报 ④ 奖金上传遇到裸 `datetime.time` 单元格直接崩溃
  ⑤ "薪资类目"页面"人力成本合计"漏加奖金/补发批次 ⑥ 导出接口疑似内存问题导致整个服务崩溃重启
  （**只诊断、没有修复**，见"未完成事项"）⑦ Mac（桌面 Safari）上传数据页完全不可用（月份选不了
  /传不了数据，`<input type="month">` 在桌面 Safari 上从来没被实现过）⑧ 上传时新实体（Blooms/
  Jupiter 等）的 Formal/Contract sheet 完全不被识别（sheet 名字识别逻辑硬编码死了只认 PP/
  Flexi 两个实体）⑨ 用户在第⑧项之后当场追加需求：单独传奖金批次时，新实体的 sheet 也要能按
  纯实体名（`PP`/`Blooms`/`Flexi`/`Jupiter`）识别。除了第⑥项，其余每项改完都单独 commit + push 到
  `claude/data-export-field-loss-fix-bsy02i`，并在用户确认后合并进线上分支
  `claude/compensation-analysis-site-un8j4k`（大多是快进合并，无冲突；有一次因为线上分支同期
  被另一个会话加了双语 UI 功能，改成了普通合并，文件没有重叠，依旧无冲突）。以下是每一项的细节：
  1. **正式工/合同工"扣款金额"字段的别名guess错误**——`FORMAL_FIELDS` 里
     `late_deduction`/`porated_days_deduction`/`absent_deduction` 三个字段的 `source_aliases`
     此前只有缩写形式（`"Late Ded."`/`"Porated Days Ded."`/`"Absent Ded."`），`CONTRACT_FIELDS`
     的 `late_deduction` 只有 `"Lateness deduction"`——这批缩写是从"权威映射文件"直接抄来的，
     从没有像同批次的其他别名那样针对真实文件复核过，而同类字段（`Hourly Late`/`Porated Days`/
     `Absent Days`）真实表头都是把词拼全的。真实导出文件里这几列 100% 为空，跟"表头缩写猜错"这个
     假设吻合。修复方式：把拼全的形式（`"Late Deduction"`/`"Porated Days Deduction"`/
     `"Absent Deduction"`）加为第一别名，原有缩写保留作为兜底别名，不删除。**注意**：如果某个月
     的批次是在这次修复之前 confirm 入库的，这个修复不会追溯生效（见"已知的坑"第 3 条），需要
     用户重新上传那个月的批次才能看到扣款金额；这不是本次改动能解决的。
  2. **奖金批次基础信息字段缺少"回落到底薪批次员工"的兜底**——`loader.py::_stage_bonus_batch`
     里 `staff_name`/`department1`/`entity` 三个字段一直都有"奖金文件自己这一列是空的话，就用
     同月同工号已入库的底薪批次员工信息兜底"的逻辑，但 `employment_type`/`department2`/
     `department3`/`position`/`reporting_line`/`job_grade`/`joining_date` 这几个同样是"基础
     信息"的字段一直没有这个兜底，只要奖金文件自己这一列没填（很常见，奖金模板本来就不会重复
     填一遍底薪批次已有的信息），这些字段就会是空的——这是一个真正的代码 bug，不是表头别名没
     对上。修复方式：新增 `_BONUS_BASE_FALLBACK_KEYS` 常量，统一给这 7 个字段套用跟
     `staff_name`/`department1`/`entity` 一样的兜底逻辑，而不是继续维护两套不一致的处理方式。
  - 新增回归测试：`tests/test_full_fields.py` 的
    `test_formal_and_contract_deduction_fields_match_spelled_out_headers`（用真实拼全的表头名
    验证别名能匹配到）和
    `test_confirmed_bonus_batch_falls_back_to_base_employee_descriptive_fields_when_blank`（验证
    奖金行自己字段为空时能从底薪批次员工兜底）。
  3. **Contract 的 `basic_salary_actual` 诊断误报**（用户用另一份真实文件上传后追问，并且明确
     确认"下载出来的数据本身是对的"）——上传时的字段匹配诊断一直对 Contract-PP/Contract-Flexi
     报"Basic Salary 未匹配到"，别名用的是 `"Monthly Basic Salary"`，但真实文件里没有这一列，
     只有 `"Actual Monthly Basic Salary"`（分析层 `salary_components.py` 一直用的就是这一列，
     导出数值本身从来没错）。这是之前"未完成事项"里记录过的一个已知诊断层面不精确，这次因为
     持续让用户误以为数据丢失，顺手改成把 `"Actual Monthly Basic Salary"` 设为第一别名（分析层
     实际读的就是这列），旧的 `"Monthly Basic Salary"` 保留作兜底别名。新增回归测试
     `test_contract_basic_salary_diagnostic_matches_real_column`。
  4. **奖金上传直接崩溃：`Object of type time is not JSON serializable`**（用户上传真实二月
     奖金文件复现，并提供了实际文件）——用真实文件定位到 `Feb Bonus-Flexi` sheet 有 11 行的
     `Joining date` 格子被 openpyxl 读成裸的 `datetime.time(0, 0)`（源文件某个环节把日期部分
     丢了，只剩时间部分），不是 `datetime.datetime`/`datetime.date`。`date_utils.py` 的
     `format_date_value()` 之前只判断了这两种类型，`datetime.time` 既不是它们的子类也不会被
     匹配到，原样往下传，最后 `json.dumps()` 序列化整行数据时才崩溃，导致**这个月的奖金批次
     完全无法上传**（比字段丢失更严重，是全量失败而不是某几列是空的）。修复：
     `format_date_value()` 新增对 `datetime.time` 的分支，转成 `"HH:MM:SS"` 字符串（跟
     datetime/date 转成字符串是同一个思路，不静默丢弃成 None），不再让整个上传崩溃。已用用户
     提供的真实文件跑通完整 `stage_upload` 流程（1565 条记录，2 个 sheet）验证过，新增回归
     测试 `test_format_date_value_converts_bare_time_objects_without_crashing`（
     `test_date_utils.py`）和 `test_bonus_batch_parser_handles_bare_time_cells_without_crashing`
     （`test_full_fields.py`）。**这类"某个字段的实际单元格类型跟预期完全不符"的问题目前只在
     `format_date_value()` 这一个入口做了兜底**——如果以后其他非日期字段也出现过 Excel 把内容
     存成意外类型（比如数字列被存成时间、文本列被存成公式对象）导致同样的 JSON 序列化崩溃，
     思路是一样的：定位到具体类型，在这个统一函数里加一个分支，而不是在每个调用点各自防御。
  5. **"薪资类目/两点比较"页面"人力成本合计"不含奖金批次**（用户自己在 Excel 里手工对账，拿
     底薪 sheet 的 HR Cost 加奖金 sheet 的总额算出正确答案，跟页面显示的数字对不上，差额正好是
     当月奖金批次总额）——`compute/categories.py` 的 `get_categories_trend()` 里"人力成本
     合计"这个类目此前只查 `MonthlyEmployeeSnapshot.hr_cost`（底薪批次），没有像 `compute/
     trends.py` 的 `get_trend()`（"趋势查询"页面用的、已验证过的口径）那样把奖金/补发的
     `SupplementalPaySnapshot.amount` 加进去，导致两个页面对"总成本"这同一个概念给出了不一致的
     数字。这是一个真正的口径遗漏，不是别名/表头问题。修复：把 `get_trend()` 里原来私有的
     `_supplemental_by_month()` 提成公共函数 `get_supplemental_cost_by_month()`（加了一个可选
     `employment_type` 参数，因为 `get_categories_trend` 支持"仅正式工/仅合同工"筛选而
     `get_trend` 不需要），在 `get_categories_trend()` 的总额模式和人均模式里，**只**给"人力成本
     合计"这一个类目叠加这部分金额（底薪/绩效薪资/奖金提成等其他类目保持不变，因为奖金/补发批次
     只有一个总金额，没有这些明细拆分，硬加会产生虚假精度）。人均模式下"人力成本合计"的均值会
     跟着调整，但**中位数依旧只基于底薪批次**（补发/奖金只发给批次里列出的部分工号，不是每个人
     都有，把月度总额平均摊给所有人再取中位数会歪曲真实分布，这是刻意保留的已知局限，代码注释里
     写清楚了）。同时处理了"某个月只有奖金批次、还没传底薪批次"这种边界情况（借用 `get_trend()`
     已经验证过的"月份取并集"处理方式），不会因为没有底薪行就丢掉那个月的奖金成本。新增回归测试
     `test_get_categories_trend_hr_cost_includes_supplemental_bonus_and_backpay`、
     `test_get_categories_trend_hr_cost_per_capita_includes_supplemental_but_median_stays_base_only`
     （`test_component_attribution.py`）。**注意范围**：`compare_departments_by_category`（部门
     对比）和 `get_cost_composition`（成本构成占比）这两个同文件里的其他函数**没有**改，依旧是
     底薪批次口径——这次只改了用户实际反馈问题的"类目趋势/两点比较"，如果以后这两个功能也被发现
     有同样的不一致，思路是复用同一个 `get_supplemental_cost_by_month()`，不要再造一个新的查询。
  6. **"下载明细"接口疑似内存问题导致整个服务反复重启（只诊断，没有修复）**——用户下载
     2025-12 至 2026-06（跨 7 个月、三种批次类型全选、不限部门/实体）时收到 502，同时贴出的
     Render 日志显示服务在没有正常部署记录的情况下反复 `Instance restarted`（大约每十几分钟
     一次）。诊断结论（详见"未完成事项"，因为没有下代码所以只在那边跟踪）：`routers/
     export.py::export_detail()` 是把请求范围内所有符合条件的行一次性在内存里拼成一整个
     openpyxl workbook 再整体转成字节流返回，不是流式/分批的；线上是 Render `starter`
     套餐，内存有限，大范围、不限批次类型/部门的导出请求行数可能有几万行，很可能把整个进程内存
     打爆导致 OOM 重启——这样炸的不只是发起下载的那个用户，是**同一时间段所有用户的请求都会
     跟着断掉**，比单纯的下载失败更严重。**这一条这次会话没有动代码**，下次接手要把它当成一个
     真实的稳定性问题来处理，不能不当回事。
  7. **Mac（Safari）上传数据页完全不可用**（用户反馈用 Mac 电脑登录时"无法上传数据、数据月份
     无法选取、看不到过往上传记录"）——根因找到并修复：`dashboard.html` 的"数据月份"用的是
     `<input type="month">`，桌面版 Safari（macOS，跟支持这个控件的 iOS Safari 不是一回事）
     从来没实现过这个输入类型，会静默退化成一个没有日期选择器、也不校验格式的纯文本框——用户
     根本没法通过原生 UI 选出合法的 `YYYY-MM` 值，`.value` 就一直是空字符串，导致
     `initUploadTab()` 的 `if (!month || ...)` 校验挡住上传、也没法触发确认——这个能直接、
     确定性地解释"月份选不了"和"传不了数据"这两条。修复：把这一个 `<input type="month">` 换成
     两个普通 `<select>`（年份 + 月份），在 JS 里拼成 `${year}-${monthNum}`——跟原生日期控件
     无关，在所有浏览器（包括桌面 Safari）上表现完全一致。年份范围是"当前年 -3 到 +1"，硬编码在
     `populateUploadMonthSelectors()`（`dashboard.js`）里，如果以后要处理更早的历史数据可能
     需要扩大这个范围。新增了一条 i18n 词条 `common.please_select`（两个 select 的占位选项，
     `i18n.js`）。用 Playwright（Chromium）冒烟测试过：两个下拉能正常填充选项、选择后能正确
     拼出 `2026-02` 这样的字符串、上传历史列表（`loadUploadHistory()`）本身照常能加载——**"看不到
     过往上传记录"这一条没有找到独立于月份选择器之外的代码层面证据**：`loadUploadHistory()`
     是完全独立于月份输入框的一次 fetch，冒烟测试里工作正常，怀疑是同一个"上传页面完全用不了"
     体验下、非技术用户把几个现象混在一起描述——如果这次月份选择器的修复上线后，用户反馈"过往
     记录"这条依然单独存在（月份能选、能上传了，但历史列表还是看不到），需要用户再单独确认一次，
     那就是另一个独立的坑，不能假设已经一并解决了。
  8. **上传时新实体（Blooms/Jupiter）的 Formal/Contract sheet 完全识别不到**（用户上传历史
     数据时反馈，用户明确列出了完整的命名规则：`Formal`/`Contract` 对应不分实体的全体正式工/
     合同工，`Formal-Blooms`/`Contract-Blooms`、`Formal-Jupiter`/`Contract-Jupiter`、
     `Formal-Flexi`/`Contract-Flexi` 分别对应各个实体自己的 sheet）——根因是
     `ingestion/constants.py` 的 `SHEET_PATTERNS` 从一开始就是按"正式工只有一种 sheet
     （`^Formal$`），合同工只有 PP/Flexi 两种（`Contract.*PP`/`Contract.*Flexi`）"这个假设
     硬编码的，新实体的 sheet（甚至只是一个大小写不同的裸 `contract`，没有 PP/Flexi 字样）
     根本没有对应的 pattern，会直接进 `unrecognized_sheet`，数据完全丢失，不是某几个字段
     缺失这种程度的问题。这次没有再加几条新的硬编码 pattern（那样下次再加一个实体又要改一次
     代码），而是把 Formal/Contract 的 sheet 识别方式换成动态提取："Formal"/"Contract"
     这个角色词本身 + 可选的实体后缀"两部分，后缀可以在角色词前面也可以在后面（`Contract -
     PP`、`PP-Contract` 都认），用空格/短横线/下划线隔开即可（`ingestion/parser.py` 新增
     `match_base_sheet_role()`）；后缀再通过 `default_entity_for_suffix()`（复用已有的
     `ENTITY_ALIASES`，"PP"→"PalmPay"这条不用重复定义）算出这个 sheet 没有自己 Entity
     列时的默认实体值。`WorkbookParseResult` 新增了 `base_sheets: dict[str, list[
     SheetParseResult]]` 字段（`formal`/`contract` 各自一个列表，因为现在一个 workbook 里
     可能有任意多个不同实体的 Formal/Contract sheet，不再是"每个角色最多一个 sheet"的假设），
     `loader.py::_stage_base()` 相应改成对列表里每个 sheet 都跑一遍同样的解析逻辑。
     `EMPLOYEE_SHEET_KEYS` 从 `["formal", "contract_pp", "contract_flexi"]` 简化成
     `["formal", "contract"]`，`ROLE_LABEL`（"合同工(PP)"这种硬编码标签）整个删掉了，诊断
     信息直接用真实 sheet 名。**这次改动完全没有改字段级别的解析逻辑**（`extract_salary_
     components`/`extract_full_detail` 等从一开始就只按 `"formal"`/`"contract"` 两个值分支，
     PP/Flexi 的区分只存在于"找哪个 sheet"这一层，不存在于"怎么解析这个 sheet 里的字段"这一层，
     所以这次改动的影响面比看起来的要小）。已经用真实的 API 请求（不只是单元测试）验证过：一个
     带 `Formal`/`contract`（裸、小写）/`Formal-Blooms`/`Contract-Blooms` 四个 sheet 的
     workbook 能正常解析出 4 个人、Blooms 的两个 sheet 正确落到 entity="Blooms"、不再出现
     `unrecognized_sheet`。新增回归测试 `test_match_base_sheet_role_recognizes_entity_
     suffix_in_either_order`、`test_default_entity_for_suffix_uses_alias_map_and_
     capitalizes`、`test_stage_base_recognizes_new_entity_sheets_without_hardcoding`
     （`test_ingestion.py`）。~~这次只改了 Formal/Contract（底薪批次）的 sheet 识别，奖金批次
     的 `bonus_pp`/`bonus_flexi` 没有推广~~——用户当场提出后续需求，已在第 9 条里一并处理了。
  9. **单独传奖金批次时，新实体（Blooms/Jupiter）的 sheet 也要能按纯实体名识别**（第 8 项刚做完，
     用户直接追加了后续需求：以后 Blooms/Jupiter 也要各自单独传奖金批次，sheet 名字就是纯实体名
     `PP`/`Blooms`/`Flexi`/`Jupiter`，不像底薪批次那样有"Formal/Contract"这个角色词可以挂靠）。
     `bonus_batch.py::parse_bonus_batch_workbook()` 本来就不按 sheet 名字过滤（每个 sheet 都会
     尝试解析，找不到工号列才跳过），所以这次真正要做的不是"识别哪些 sheet"，而是"sheet 自己没有
     Entity 列时，怎么从 sheet 名猜出默认实体"。新增 `ingestion/parser.py::
     entity_hint_from_sheet_name()`：只有当 sheet 名字整个就是一个"裸词"（`^[A-Za-z][A-Za-z0-9]*$`，
     没有空格/短横线/其他文字混在一起）才会尝试当作实体名，这样能正确拒绝像 `Feb Bonus-PP` 这种
     "实体名混在其他文字里"的真实历史文件名（那种文件本来就是靠自己的 Entity 列，不需要也不应该
     被这个新逻辑影响）。**光有"裸词"这一条判断还不够**——开发过程中自己写的回归测试就先抓出一个
     问题：如果不加限制，一个单纯叫"Bonus"的 sheet 也会被误判成"实体名是 Bonus"。所以又加了一层
     "这个词是不是系统里已经真实存在的实体"的校验：`ENTITY_ALIASES`（"PP"→"PalmPay"）这种明确
     维护的别名表直接认，除此之外必须是 `MonthlyEmployeeSnapshot` 里已经出现过的实体名（不分月份，
     只要历史上任何一个月出现过就算数，大小写不敏感）才会被采信——这个校验列表是
     `loader.py::_stage_bonus_batch()` 在调用解析函数之前现查数据库现算出来的（`known_entities`
     参数），不是写死的名单，所以以后再加新实体不需要改代码，只要那个实体的 Formal/Contract 底薪
     批次先传过一次（现实中的上传顺序本来也是先传底薪批次、奖金批次是月度流程里后传的，这个假设
     合理）。为了让这个"entity 字段其实是从 sheet 名猜出来的，不是这个 sheet 缺列"的信息能传到
     字段匹配诊断那一层，避免又出现一次"Entity 未匹配"的假警报（跟这次会话第③项修的
     basic_salary_actual 诊断误报是同一类问题——已经明确写进"已知的坑"，这次是主动按这个教训去
     检查、提前避免的，不是又被用户发现一次），`full_fields.py::check_field_mapping()` 新增了
     `satisfied_elsewhere` 参数（一个"这个字段就当作已经匹配上，不用检查表头"的 key 集合），
     `ingestion/parser.py::SheetParseResult` 新增了 `entity_hint` 字段，Formal/Contract（第 8
     项）和奖金批次两边现在都会在有 entity_hint 的时候把 `"entity"` 传进
     `satisfied_elsewhere`。已经用真实的 API 请求验证过完整链路：先传一个 `Formal-Blooms` 底薪
     批次确认入库，建立"Blooms 是已知实体"这个前提，再传一个有 `Blooms`/`PP` 两个 sheet（都没有
     Entity 列）的奖金批次，两个 sheet 的字段匹配诊断都是"24 个全部匹配 ✓"（没有假警报），下载
     导出的奖金明细里 Entity 列正确显示 `Blooms`/`PalmPay`。新增回归测试
     `test_entity_hint_from_sheet_name_only_matches_bare_known_entity_names`
     （`test_ingestion.py`）、`test_bonus_batch_parser_resolves_entity_from_bare_entity_
     sheet_name`、`test_bonus_batch_parser_does_not_guess_entity_from_descriptive_sheet_
     name`、`test_confirmed_bonus_batch_resolves_entity_from_sheet_name_end_to_end`
     （`test_full_fields.py`）。142 个测试全部通过。

## 未完成 / 待跟进事项

- **"下载明细"大范围导出可能导致整个服务 OOM 重启（上面第 6 条，优先级最高，涉及服务可用性）**：
  复现条件是"月份范围较大 + 批次类型全选/不限部门实体"，现象是导出请求 502，同时 Render 日志
  显示服务在没有正常部署的情况下反复重启。还没有拿到 Render Metrics 页的内存曲线做最终确认
  （这个沙盒环境连不上生产环境，见下面第 4 条已知的坑），但代码本身（`export.py` 一次性在内存
  里拼完整个 workbook）足够可疑，值得直接着手做防护，不必等内存曲线证实：思路可以是
  (a) 给单次导出加一个最大行数/最大月份跨度的软上限，超出时返回明确的 400 提示而不是硬扛，
  (b) 或者把 `openpyxl.Workbook()` 换成 `write_only=True` 的流式写入模式，避免整份文件常驻内存。

- **这次导出文件里还有其他字段是空的，但不在这次任务范围内，没有动**：用户这次附的真实一月导出
  文件里，合同工明细的 `Reporting Line`/`Work Station`/`Should Work Days`/`Airtime/Data
  Allowance`/`Overtime Hours`/`Other Income` 也是整列 100% 空的——其中前四个按理说应该已经被
  上一轮热修复（`Chinese Reporting line`/`Work Location`/`Should Working Days`/更长的话补列名）
  覆盖到了，但这份导出里依旧全空。这次会话只处理了用户明确点名的"扣款金额"和"奖金基础信息"两类，
  没有去查这几个字段——**优先怀疑是这批数据是在上一轮热修复之前 confirm 入库的旧数据**（见"已知
  的坑"第 3 条，旧数据不会因为代码修复而自动更新），需要先确认用户是否已经用修复后的代码重新
  上传过这个月的批次；如果重新上传后这几个字段依旧是空的，那才说明上一轮的别名修复本身有问题，
  需要另外排查（比如这个真实文件里合同工的表头写法比之前验证过的两种更多）。
- **线上分支同期多了一个双语 UI 功能，不是本次会话做的**：合并本次会话最后一项修复时发现
  `claude/compensation-analysis-site-un8j4k` 上多了一个不在本次会话记录里的提交"Add bilingual
  (Chinese/English) UI with a language toggle"（新增 `frontend/static/js/i18n.js`，给
  `dashboard.html`/`login.html` 全面加了 `data-i18n` 属性和中英文切换），应该是另一个并行会话
  做的。跟本次会话的改动文件没有重叠，合并时没有冲突，但下次接手如果发现前端文案改成
  `data-i18n="xxx"` 这种写法、多了个语言切换开关，不用惊讶——不是这份 HANDOFF 记录的哪一轮改的，
  具体决策细节要去看那个提交自己的 commit message。
- ~~合并到 main 分支~~——**本次会话已核实这一条过时了**：仓库里根本不存在 `main` 分支，
  `claude/compensation-analysis-site-un8j4k` 本身就是 Render 实际部署的分支（见"部署信息"），
  不存在"还没合并到 main 所以没生效"的问题。以后不用再纠结这一条，除非用户明确要求另建一个
  `main` 分支。
- **GitHub 仓库疑似改名**：`git push` 时远端一直提示"This repository moved. Please use the
  new location: https://github.com/Marcuswu0720/compensation-analysis-system.git"，早前
  已经提醒过用户，用户没有回应。目前推送仍然通过重定向成功，不算紧急阻塞项，但如果未来推送突然
  失败，先查这个仓库地址是否需要更新 remote。
- **README"已知限制"里还挂着的开放问题**（都是需要用户用真实数据继续验证、不是可以单方面关闭
  的任务）：
  - 权责发生制下奖金按业绩归属月拼接的完整口径还没做，目前用的是现金流口径（`HR Cost`），跟
    PRD 验证过的基准数字一致，但如果以后要看"3月的绩效奖金应该算到哪个月的成本里"这类权责发生制
    问题，需要新功能。
  - 跨部门转岗员工的历史轨迹追溯、薪酬 benchmark 联动：说好留到后续版本，还没开始设计。
  - `gross_salary`（税前薪资总额）目前是直接读原始表现成列，不是重新加总算出来的，真实数据里
    大约 1-2% 的记录跟"底薪+绩效+奖金+加班+其他收入"加总对不上（原始表本身的调整，不是解析
    错误），校验摘要会报出这类记录数量供人工抽查，但没有更进一步的自动核对逻辑。
  - ~~Contract 的 `basic_salary_actual` 诊断别名~~——已在"V1.9 热修复之后的第二轮"第 3 条修复，
    诊断改成检查 `"Actual Monthly Basic Salary"`（分析层实际读的列），不再对真实文件误报。
  - 奖金批次的 Job Grade：已确认真实文件本身就没有这一列，不是软件的匹配问题——如果以后 HR
    换了新模板加上了这一列，不需要改代码，`check_field_mapping` 会自动认出来。
- **问答模块**：目前只是关键词/正则匹配（`qa/rule_engine.py`），能识别的月份格式和部门中文
  关键词都是硬编码的，问法差太远会识别失败。如果以后想升级成能自由对话的版本，说好的方案是换掉
  `chat.py`、接一个大模型 API 做 tool use，`compute/` 计算层不需要改（因为已经是"确定性代码+
  模板套数字"的架构，LLM 只需要负责把用户的自然语言路由到正确的 compute 函数调用，不需要也不
  应该自己算数字）。

## 已知的坑（下次改动前先看这里，避免重复踩雷）

1. **`parse_workbook()` 对每个角色（正式工/合同工-PP/合同工-Flexi/奖金-PP/奖金-Flexi/离职）都
   返回非 `None` 的 `SheetParseResult`**，哪怕这个月的文件里根本没有这个 sheet（此时
   `sheet_name` 是 `None`，`rows` 是空列表）。任何要判断"这个 sheet 这个月存不存在"的新代码，
   必须判断 `sheet_result.sheet_name is None`，不能用 `if not sheet_result` 这种真值判断——
   V1.8 就因为这个判断错误产生过真实的误导性诊断。
2. **同一个逻辑字段，在 Formal / Contract-PP / Contract-Flexi / Bonus 这几类 sheet 里，原始
   表头的具体写法可能完全不同**——不能假设"这个字段在所有 sheet 类型里都叫同一个名字"。目前
   已知的差异见上面 V1.9 热修复那条，但不保证这是全部——如果以后又出现某个字段在某类 sheet 里
   读不到，先怀疑是不是表头写法不一样，而不是解析逻辑坏了。
3. **历史数据的"只读不改"问题**：任何一次字段映射/日期格式的修复，只对**修复之后新上传确认**
   的批次生效。已经 confirm 入库的旧批次，其 `full_detail_json`/日期字段是在当时的（可能有
   bug 的）逻辑下写死存进数据库的，修复代码本身不会自动回溯改正旧数据——除非该次修复是"值本来
   就抓到了，只是显示格式不对"这种可以在读取/导出时二次处理的情况（比如日期后缀），否则唯一的
   修复方式是删除并重新上传那个月的批次。跟用户沟通"这个数据为什么还是不对"时要先分清楚是这两种
   情况里的哪一种。
4. **本地开发/测试环境不能访问 Render 生产数据库**——这个沙盒环境是隔离的，任何"生产环境显示
   不对"的反馈，只能靠用户提供真实文件在本地复现（而不是假设本地能连到线上库去看），也没有办法
   帮用户在生产库上跑数据修复脚本，只能通过让用户重新上传来触发修复后的代码路径。
5. **Contract 的雇主社保成本 = 现成的 `ER COST` 列，不要再假设是 NSITF+Pension ER+ITF+HMO 的
   加总**——这是 V1.1/V1.5 时代的一个错误假设，V1.8 已经用权威映射文件纠正，不要因为看到 NSITF/
   Pension/ITF/HMO 这些列还在原始表里就以为需要重新加总。
6. **迁移脚本是手写的，不是 Alembic**——加新列时记得同时改 `migrations.py`（对应表的列名/类型
   字典）和 `models.py`，两处不同步会导致新代码读不到刚加的列，或者列加了但 ORM 模型不知道。
7. **`verified=True`/"已经跟权威映射文件核对过"不等于"真的针对真实文件测试过"**——本次会话修的
   正式工/合同工扣款金额三个字段，别名从 V1.8 建立起就标了 `verified=True`（因为字面上是抄自
   权威映射文件"数据导出展示字段-映射.xlsx"），但那份映射文件给的可能是缩写/截断文本，从没拿一份
   真实文件实际核对过表头长什么样。以后新加/信任一条别名，`verified=True` 只应该表示"拿真实文件
   核对过"，不能表示"抄自某份文档、看起来像是权威来源"——这两者不是一回事，本次这几个字段就是
   混淆了两者才漏网的。
8. **测试用"FieldSpec 自己的别名"生成假表头，测不出真实文件的别名错误**——`test_full_fields.py`
   里有一类历史测试（比如 V1.8 时代写的"字段匹配诊断全部匹配"测试）是拿 `FORMAL_FIELDS` 等清单
   自己声明的 `source_aliases` 反过来拼一份"假表头"喂给解析函数，这种测试对"函数逻辑本身没写错"
   有意义，但对"这个别名到底对不对"完全没有验证力——别名如果本来就猜错了，用别名自己生成的假表头
   永远会"验证通过"，这是一种循环论证。新增字段别名的回归测试，应该像本次会话新加的几条一样，
   用不依赖该别名本身拼出来的、看起来像真实表头的字符串（最好是真的从用户文件里抄的）。
9. **"总成本/人力成本"这个概念在代码里不是只有一处实现**——`compute/trends.py::get_trend()`（
   趋势查询页面，会把底薪+奖金+补发都加总，是这几处里最先做对、也是本次会话认定的"标准答案"）、
   `compute/categories.py::get_categories_trend()`（薪资类目页面，本次会话修复后"人力成本合计"
   这一项也对齐了）、`compute/categories.py::get_cost_composition()`（成本构成占比，依旧只有
   底薪批次，没有对齐）、`compute/categories.py::compare_departments_by_category()`（部门对比，
   同样依旧只有底薪批次）——后两个如果以后被发现跟用户预期的"总成本"对不上，别再各自加一段查询
   逻辑，复用 `compute/trends.py::get_supplemental_cost_by_month()`。
10. **Excel 单元格的实际 Python 类型可能跟表头暗示的完全不符**——本次会话遇到一个"Joining Date"
    列里混进了裸的 `datetime.time` 值（不是 `datetime.datetime`/`datetime.date`）导致
    `json.dumps()` 直接崩溃整个上传。目前这类"意外类型"兜底只在 `date_utils.py::
    format_date_value()` 这一个入口做了处理（覆盖 `datetime`/`date`/`time` 三种），如果以后
    别的字段也遇到类似的意外类型（比如公式单元格、合并单元格返回 `None` 之外的怪值），思路一样：
    定位到具体类型，在这个统一入口加分支，不要在各个调用点分别 try/except 兜底。
11. **前端不要用 `<input type="month">`/`type="date"`/`type="week"` 这类原生日期控件——桌面版
    Safari（macOS）对这几种类型的支持历史上一直不完整，`type="month"` 干脆就没实现过**，会静默
    退化成一个没有选择器、不做格式校验的纯文本框，用户根本没法通过 UI 输入出合法值，`.value`
    只会是空字符串——这不是某个浏览器版本的临时 bug，是桌面 Safari 长期以来的已知限制（注意
    "桌面版"和"iOS 版" Safari 支持情况不一样，不能拿 iPhone/iPad 上测试过就当作桌面也没问题）。
    本次会话把"上传数据"页的月份选择器换成了两个 `<select>`（年份+月份）规避这个问题，这个模式
    应该作为以后所有"日期/月份选择"UI 的默认做法——除非明确知道目标用户只用 Chrome/Edge/Firefox
    这类完整支持原生日期控件的浏览器。

## 部署信息

- Render Blueprint 部署（`render.yaml`）。仓库里根本没有 `main` 分支（`git branch -a` 只有两个
  `claude/*` 分支），线上 Render 服务实际连接、配置了"推送后自动部署"的是
  `claude/compensation-analysis-site-un8j4k`——之前几版 HANDOFF 里"push 到 main 才部署、还没
  合并到 main"的说法不准确，这个分支本身就是当前的部署分支，不需要等合并到某个不存在的 `main`。
- **但"推送后自动部署"这一步本次会话亲身踩过坑，不能想当然认为"push 了就等于线上生效了"**：
  合并到 `claude/compensation-analysis-site-un8j4k` 后，用户反馈 Mac 上看到的还是修复前的旧
  页面；一开始怀疑是浏览器缓存，但去 Render 的 Deploys 页面核实后发现——**最新的推送根本没有
  触发自动部署**，Deploys 列表最上面（Live）的那条还是好几个提交之前的旧记录。日志里能看到的
  `==> Instance restarted`/`Running 'python -m uvicorn...'` 记录**不能当作"部署了新代码"的
  证据**——这两者是完全不同的东西：容器因为别的原因（比如已经诊断过的下载大文件导致 OOM）被
  平台重启，只是把同一份旧代码重新跑起来，跟拉取新提交、重新构建完全无关；只有 Deploys 页面
  列表里出现新的一条、并且标成 Live，才说明新代码真的上线了。这次是让用户手动点击右上角
  **"Manual Deploy" → "Deploy latest commit"** 才解决的。**以后每次合并推送到这个分支之后，
  如果用户反馈"看起来没生效"，第一反应应该是让用户去 Deploys 页面核对最新一条部署对应的
  commit，而不是先假设是缓存问题**——缓存问题当然也可能存在，但部署没触发是更值得先排除的
  可能性，且更容易验证（直接看 Deploys 列表）。这个沙盒环境连不上 Render 后台，没法主动触发
  或核实部署，只能靠用户截图确认。
- SQLite 数据库文件挂载在 Render 的持久磁盘上（`/var/data/app.db`），`SECRET_KEY` 由 Render
  自动生成，`ADMIN_USERNAME`/`ADMIN_PASSWORD` 需要在 Render 后台手动配置（`sync: false`）。
- 本地测试：`cd backend && python -m pytest tests/ -v`，测试全部用合成数据
  （`tests/xlsx_fixtures.py` 现造的假工作簿），不含任何真实员工信息，可以放心提交到仓库。这个
  沙盒环境连不上 Render 生产数据库/生产日志，只能靠用户提供真实文件或截图（比如 Render Logs
  页面截图）来复现问题，见"已知的坑"第 4 条。
