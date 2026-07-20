# 企业考勤管理系统

面向中小企业（尼日利亚场景）的考勤管理平台，覆盖打卡、请假加班审批、考勤统计、组织架构与规则配置。详细需求见项目交流记录中的《企业考勤管理系统 - 需求文档》。

当前范围：单地区（尼日利亚），暂未做多地区 `regionId` 隔离；技术栈按需求文档建议实现。

## 技术栈

| 层级 | 技术选型 |
|---|---|
| 前端 | React 18 + TypeScript + Vite + Ant Design + React Query + Zustand |
| 后端 | NestJS + Prisma + PostgreSQL |
| 鉴权 | JWT (Access + Refresh Token) + RBAC，总部账号在网关层强制只读 |
| 文件存储 | 本地磁盘（`backend/uploads`），生产环境建议替换为 S3 兼容对象存储 |
| 部署 | Docker Compose（Postgres + 后端 + 前端） |

## 目录结构

```
attendance-system/
├── backend/          # NestJS API 服务
│   ├── prisma/       # 数据模型 schema.prisma、迁移、seed 脚本
│   └── src/          # 按业务模块划分（auth/users/departments/teams/offices/
│                      #   attendance/special-events/schedules/location-checkin/
│                      #   rule-templates/leave/overtime/reports/holidays/common）
├── frontend/          # React + Vite 前端
│   └── src/
│       ├── api/       # 后端接口封装 + 类型定义
│       ├── pages/      # 按第12节路由清单组织的页面
│       └── store/       # 登录态（zustand + 本地持久化）
└── docker-compose.yml
```

## 快速开始（本地开发）

### 1. 启动数据库

```bash
docker compose up -d postgres
# 或本机已有 PostgreSQL 服务，确保 backend/.env 中 DATABASE_URL 指向可用的库
```

### 2. 启动后端

```bash
cd backend
cp .env.example .env   # 按需修改
npm install
npx prisma migrate dev
npx prisma db seed      # 生成演示数据（部门/团队/办公室/演示账号）
npm run start:dev       # http://localhost:3000/api
```

### 3. 启动前端

```bash
cd frontend
cp .env.example .env
npm install
npm run dev              # http://localhost:5173
```

### 4. 演示账号（密码统一为 `Passw0rd!`）

| 邮箱 | 角色 | 说明 |
|---|---|---|
| hq.admin@example.com | 总部（只读） | 全局报表只读，无法写任何规则/审批接口 |
| hr@example.com | 本地HR/HRIS | 组织架构、规则配置、审批、特殊事件标记 |
| manager@example.com | 本地小管理者 | 定位打卡核实、本地区报表 |
| amaka@example.com | 员工（办公室打卡） | IT团队，模式1 |
| emeka@example.com | 员工（排班打卡） | 线上收单-KA团队，模式2 |
| ifeoma@example.com | 员工（地催，办公室打卡+最近网点自动分配，只打上班卡） | 分期-催收-地催团队，7.1节细分规则 |
| tunde@example.com | 员工（定位打卡+业务指标出勤） | SME-BD-码牌团队，7.1节细分规则 |

## 用 Docker Compose 一键启动全栈

```bash
docker compose up -d --build
# 首次启动后手动执行一次 seed（可选）：
docker compose exec backend npx prisma db seed
```

## 已实现范围（对照需求文档第15节的九个开发阶段）

- [x] 阶段1：JWT鉴权 + RBAC（含总部账号网关层强制只读）+ 部门树 + 团队与打卡模式映射（第2、3章）
- [x] 阶段2：办公室打卡（迟到/早退宽限规则可配置）+ 特殊事件全勤自动标记与撤销回退（第4章）
- [x] 阶段3：排班打卡（班次定义、批量生成、临时换班留痕）（第5章）
- [x] 阶段4：定位打卡（照片+GPS+核实工作流：待核实/通过/驳回）（第6章）
- [x] 阶段5：请假/加班申请与审批，审批通过后自动联动考勤记录（第8章）
- [x] 阶段6：考勤统计报表（个人日历、本地区报表、全局报表、CSV导出）（第9章）
- [x] 阶段7：管理后台（员工管理含Excel批量导入、部门/团队管理、考勤规则配置页）（第10章）
- [x] 阶段8：团队级规则模板引擎（是否打卡/是否需要照片/业务指标出勤判定）+ 打卡轨迹视图（第7章）
- [x] 阶段9：统一审计日志（贯穿所有写操作）+ 总部只读权限收尾（第11章）

## 需求文档第14节「待确认事项」— 当前实现采用的默认假设

以下事项文档中标注为待确认，为完成可运行的骨架系统，本次实现采用了以下默认假设，后续需与业务确认后调整：

1. **面签团队 GPS 轨迹打卡**：已实现"打卡照片+工作日报"现状路径（`TeamAttendanceRuleTemplate.requiresPhoto`），GPS 轨迹的"理想方案"可通过同一套 `LocationCheckInPhoto` 上传+轨迹视图能力支持，无需额外开发，只需调整该团队的规则模板配置。
2. **码牌团队部署量数据来源**：当前实现为人工录入（`businessMetricValue` 随打卡照片一起提交），`businessMetricSource` 字段预留 `API` 选项，待业务系统 API 确认后可接入。
3. **异常预警通知渠道**：当前仅记入审计日志（`LOCATION_CHECKIN_ANOMALY`）供质检团队查阅，未接入短信/邮件/站内信，需确认后补充通知渠道。
4. **较稳定/不稳定排班**：底层使用同一套 `Shift` + `ScheduleAssignment` 结构，未做 UI 差异化。
5. **多地区扩展**：本次只做尼日利亚单地区，未加 `regionId` 隔离字段；后续多地区扩展需在规则相关表补充该字段并调整查询过滤。
6. **企业微信/钉钉对接**：未实现，如需要可在审批通知、异常预警等场景接入。
7. **人脸识别等生物识别打卡**：未实现，当前定位打卡以人工核实照片为准。

## 尚未做的事（建议后续迭代）

- 生产级对象存储（当前为本地磁盘存储打卡照片）
- 定时任务：如"排班日无打卡自动标记缺勤"，当前仅在员工主动打卡/请假审批时更新考勤记录
- 前端国际化（多语言）与更细粒度的移动端优化
- 单元测试/E2E 自动化测试覆盖
