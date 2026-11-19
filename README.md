# AgentOps Studio

**Open-source DTC operations workflow automation | FastAPI · SQLite · REST · Rules/Optional LLM · Human-in-the-loop**

[中文](#快速开始) | [Architecture](docs/ARCHITECTURE.md) | [Data contracts](docs/DATA_CONTRACTS.md) | [Security](SECURITY.md)

AgentOps Studio 是一个**可以实际导入业务数据并执行分析工作流**的独立开源项目，不属于任何被引用品牌或招聘公司。它面向 DTC 客户反馈、广告归因分析、KOL 合作筛选与管理决策。工作流是真的：读取持久化的行数据、计算指标、保存逐步执行结果、生成需要人工审批的建议，并提供可导出的 Markdown 简报。它**不会**擅自修改广告预算、发送客户消息或联系达人。

### 功能与状态

| 模块 | 输入 | 实际处理与输出 | 状态 |
|---|---|---|---|
| 用户反馈 VOC | CSV / JSON 评论、评分 | 关键词分组、风险优先级、证据 ID、人工复核任务 | 已实现（确定性规则） |
| 广告分析 | 投放、点击、转化、成本、归因营收 | ROAS/CTR/CVR/CPA、预算调整草案 | 已实现（归因非因果增量） |
| 达人筛选 | 粉丝、互动、匹配度、报价、异常标记 | 可解释评分、短名单、待审合作建议 | 已实现（非真实转化预测） |
| CEO简报 | 以上三类导入数据 | 提取优先事项，引用来源记录，导出 Markdown | 已实现 |
| 审批与审计 | 待审建议、人工决定 | 状态变更、审批事件、审阅理由 | 已实现 |
| 数据接入 | UTF-8 CSV / JSON REST | 验证字段、数值范围、事务导入、SQLite持久化 | 已实现 |
| 调度 | 本地CLI + cron/任务计划程序 | 周期执行与同输入去重 | 已实现 |
| 业务问答 | 当前数据及内置 SOP | 默认确定性规则；可配置 OpenAI 兼容接口 | 已实现；LLM依赖自有密钥 |
| n8n / MCP | 示例适配器 | 工作流编排示例 / 可选 MCP 服务源码 | 未做目标环境集成验收 |

**限制**：目前是单操作员本地部署的开源工程样板；不是生产级 SaaS，不包含真实 Shopify/TikTok/Meta 授权、RBAC、多租户、向量 RAG、自动广告调价、在线流式事件或可靠的投放增量因果评估。为保护用户，外部破坏性动作均不自动执行。

## 快速开始

需要 Python 3.10+。首次安装依赖需网络，之后规则工作流可以离线运行，CPU 即可，无需 GPU。

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

浏览器访问 **http://127.0.0.1:8765**，可使用交互式 REST 文档 **http://127.0.0.1:8765/docs**。Windows 可以双击 `start_windows.bat`，Mac/Linux 运行 `bash start_mac_linux.sh`。

首次运行**不生成任何虚构客户数据**。从“业务数据中心”导入自己的 UTF-8 CSV；字段约定见 [DATA_CONTRACTS](docs/DATA_CONTRACTS.md)。也可以通过 JSON API：

```bash
curl -X POST 'http://127.0.0.1:8765/api/datasets/feedback/ingest' \\
  -H 'Content-Type: application/json' \\
  -d '[{"id":"F1","channel":"Web","product":"Recorder","market":"US","rating":2,"comment":"Export fails during save","created_at":"2026-11-19"}]'
curl -X POST http://127.0.0.1:8765/api/workflows/run-all
curl http://127.0.0.1:8765/api/approvals
curl http://127.0.0.1:8765/api/brief.md
```

也支持终端导入和定时处理：

```bash
python -m app.cli import-csv feedback data/example_feedback.csv
python -m app.cli import-csv campaigns data/example_campaigns.csv
python -m app.cli import-csv creators data/example_creators.csv
python -m app.cli run
python -m app.cli run --every 3600
```

上述 `example_*.csv` 是**虚构数据**，用于仅本地测试。要自动填充完整虚构样例，启动前显式指定 `AGENTOPS_SEED_SAMPLE=1`；普通使用不要设置，默认是 `0`。

## Docker

```bash
docker compose up --build -d
```

Docker Compose 默认只发布到 **127.0.0.1:8765**；数据库存储在 Docker volume 内。只有在自行建立TLS反向代理、鉴权及访问控制后才应允许他人访问。详见 [SECURITY.md](SECURITY.md)。

## API和安全边界

- 默认只允许本机直接调用数据接口；跨域写请求被拒绝。
- 可配置环境变量 `AGENTOPS_API_TOKEN`，通过 `Authorization: Bearer <token>` 调用接口；浏览器首次收到401会提示输入，会话期间保存在 `sessionStorage`。这是**单操作员口令**，不是 RBAC 或企业级登录。
- 所有业务数据、运行记录及审批事件持久化为 SQLite，数据库文件与密钥均被 `.gitignore` 排除。
- 相同输入快照默认只计算一次并复用此前结果；若要强制重新计算，`POST /api/workflows/{slug}/run?force=true`。强制执行会生成新的审批草案。
- 不执行对外投放、转账、签约、客服外发等副作用；审批结果仅在本地记录。
- 可选模型调用需配置 `OPENAI_COMPAT_API_KEY` 和相应端点，启用后问题和数据摘要会离开本机发送至你指定的第三方服务，**不要上传未经授权的真实客户数据**。

## 测试 / CI

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

项目包含 GitHub Actions（Python 3.11、3.12）持续集成，覆盖空库默认值、实际数据导入、规则分析、审批审计、访问控制、输入幂等和无效记录拒绝。CI通过不等于线上业务效果已验证。

## 项目结构

```text
app/              FastAPI、数据存储、确定性工作流、CLI、可选模型接口
web/              单页应用，无第三方前端构建依赖
data/example_*.csv 仅供开发者主动导入的虚构示例
integrations/     n8n流程样例、MCP适配器（未做端到端连接验收）
tests/            API与工作流自动化测试
.github/workflows/ci.yml  自动运行测试
docs/             数据契约、架构、截图、GitHub 发布指引
```

## GitHub 发布

仓库准备步骤见 [GITHUB_RELEASE.md](docs/GITHUB_RELEASE.md)。只推送代码和示例文件，不推送私有数据、凭证、数据库或真实客户记录。开源协议：MIT。
