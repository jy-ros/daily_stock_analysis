# AGENTS.md

本文件是本仓库 AI 协作规则的唯一真源（`CLAUDE.md` 是指向本文件的软链接）。目标是减少重复沟通、减少返工，让改动与当前项目结构保持一致。若与脚本、工作流、代码现状不一致，以实际可执行内容为准，并在相关改动中顺手修正文档。

## 1. 硬规则

- 遵循现有目录边界：
  - 后端：`src/`、`data_provider/`、`api/`、`bot/`
  - Web：`apps/dsa-web/`
  - 桌面端：`apps/dsa-desktop/`
  - 部署 / Workflow：`scripts/`、`.github/workflows/`、`docker/`
- 未经明确确认，不执行 `git commit`、`git tag`、`git push`、`gh pr create`。
- commit message 使用英文，不添加 `Co-Authored-By`。
- 不写死密钥、账号、端口、模型名或在库中硬编码本机路径 / 环境差异逻辑。
- 优先复用现有模块、配置入口、脚本和测试，不新增平行实现。
- 默认稳定性优先于"顺手优化"；与当前任务无关的重构一律克制。
- 新增配置项必须同步 `.env.example`；涉及用户可见能力、CLI/API 行为、部署方式、通知方式、报告结构变化时，必须同步相关文档与 `docs/CHANGELOG.md`。
- 修改报告格式、渲染效果或 Web UI 时，PR 描述必须附受影响截图；前后有差异时优先附对比。临时截图、审查截图不上库，放 PR 描述/评论或附件。
- `docs/CHANGELOG.md` 的 `[Unreleased]` 段使用扁平格式：每条 `- [类型] 描述`（`新功能`/`改进`/`修复`/`文档`/`测试`/`chore`），禁止在 `[Unreleased]` 内新增 `### 类目标题`。
- `README.md` 只放首页级信息；详细行为、页面交互、配置、排障、字段契约放 `docs/*.md`。
- 变更中英文双语文档之一时，评估另一份是否需同步；未同步需写明原因。
- 注释、docstring、日志文案以清晰准确为准，不强制英文，但应与文件语境一致。

## 2. 代码风格

- **格式化**：`black`（line-length=120）+ `isort`（profile=black, line_length=120）。flake8 忽略 `E501/W503/E203/E402`，关注运行错误：`flake8 . --count --select=E9,F63,F7,F82`。
- **导入**：stdlib → 三方 → 本仓库模块三段式；优先 `from x import y`；模块顶部加 `from __future__ import annotations`。
- **类型**：公开函数/方法尽量写类型注解；结构化结果优先 `@dataclass`，有限状态优先 `Enum`（见 `src/stock_analyzer.py` 的 `TrendStatus`/`MACDStatus`）。
- **命名**：函数/变量 `snake_case`，类 `CamelCase`，常量全大写；模块与目录边界对齐（`src/` 下按 core/services/repositories 分层）。
- **错误处理**：优先"局部失败不拖垮主流程"，用 `logger.warning/exception` + 优雅降级，不静默吞异常，也不能用 broad fallback / `return None` 掩盖契约。跨版本读取字段用 `getattr(obj, 'field', default)`。
- **并发**：重任务用 `ThreadPoolExecutor`（reuse pipeline 的 `max_workers`），共享资源注意线程安全，单任务异常需隔离。
- **日志**：`logger = logging.getLogger(__name__)`，camelCase 结构跟随业务，关键节点用`[component] action=...` 风格。

## 3. 仓库速览

- 项目定位：股票智能分析系统，覆盖 A 股、港股、美股。主流程：抓取数据 → 技术分析/新闻检索 → LLM 分析 → 生成报告 → 通知推送。
- 关键入口：`main.py`（CLI）、`server.py`（FastAPI）、`apps/dsa-web/`（Web）、`apps/dsa-desktop/`（Electron）。
- 核心目录：`src/core/` 主流程编排、`src/services/` 业务服务、`src/repositories/` 数据访问、`src/reports/` 报告、`src/schemas/` 数据结构、`data_provider/` 多源 fallback、`api/`、`bot/`、`scripts/`、`tests/`、`docs/`。

## 4. 常用命令

### 运行

```bash
python main.py                       # 完整分析
python main.py --dry-run             # 仅取数据不分析
python main.py --stocks 600519,hk00700,AAPL --no-market-review
python main.py --market-review
python main.py --schedule | --serve | --serve-only
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

### 后端验证

```bash
pip install -r requirements.txt
./scripts/ci_gate.sh                     # 完整后端 gate（语法+flake8+确定性+离线测试）
./scripts/ci_gate.sh syntax             # 仅语法检查
./scripts/ci_gate.sh flake8             # 仅静态检查
python -m pytest -m "not network"       # 离线测试（跳过 network 标记）
```

### 跑单个测试（优先用路径+冒号定位）

```bash
python -m pytest tests/test_notification_sender.py -m "not network"
python -m pytest tests/test_notification_sender.py::TestClass::test_name -m "not network"
python -m pytest tests/test_pipeline_realtime_indicators.py -k "macd or divergence"
python -m py_compile <changed_python_files>
```

标记：`unit`（离线单元） / `integration`（无外部网络的服务级） / `network`（需外网，默认不跑）。

### Web / Desktop

```bash
cd apps/dsa-web && npm ci && npm run lint && npm run build
cd ../dsa-desktop && npm install && npm run build
```

### PR / CI 证据

```bash
gh pr view <pr_number> && gh pr checks <pr_number>
gh run view <run_id> --log-failed
```

## 5. 默认工作流

1. 判断任务类型：`fix / feat / refactor / docs / chore / test / review`。
2. 先读现有实现、配置、测试、脚本、工作流和文档，再动手。
3. 识别改动边界与高风险区：配置语义、API/Schema、数据源 fallback、报告结构、认证、调度、发布流程、桌面端启动链路。
4. 只做最小改动，不夹带无关重构；发现文档与代码不一致时优先信任代码再修正文档。
5. 按验证矩阵执行检查，交付需说明：改了什么 / 为什么 / 验证情况 / 未验证项 / 风险点 / 回滚方式。

## 6. 验证矩阵

- **Python 后端**：`./scripts/ci_gate.sh`；至少 `python -m py_compile <changed>`。影响 API/任务编排/报告/通知/数据源 fallback/认证/调度时说明覆盖路径。
- **Web**：`npm ci && npm run lint && npm run build`；涉及联调/路由/状态/Markdown 渲染/认证时说明联动面与风险。
- **桌面端**：先构建 Web 再构建桌面端；平台受限时说明验证范围。
- **API/Schema/认证联动**：后端验证 + 受影响客户端构建验证；字段/枚举变化必须写明兼容性影响。
- **文档/治理**：核对命令、配置、文件名、workflow 是否与实际一致；改 AI 治理资产跑 `python scripts/check_ai_assets.py`。
- **workflow/脚本/Docker**：跑最接近改动的本地验证，说明影响的流水线/发布路径，未跑 GitHub Actions 时写明原因。
- **网络/三方依赖**：先跑离线确定性检查；重点确认 timeout/retry/fallback/降级路径是否成立。

CI 项：`ai-governance`（阻断）、`backend-gate`（阻断）、`docker-build`（阻断）、`web-gate`（触发时阻断）、`network-smoke`（观测）、`pr-review`（辅助）。已存在 CI 结论可直接引用。

## 7. 稳定性护栏

- 新配置默认"不配置可运行，配置后增强能力"，避免叠加开关和互斥模式。
- 修改 `data_provider/` 要关注优先级、失败降级、字段标准化、缓存与超时；单数据源失败不拖垮主流程。
- 改 API/Schema/认证/报告载荷时同时检查后端、Web、Desktop；优先追加字段或保留旧字段。
- 改报告 / Prompt / 通知时检查上游输入与下游消费方；单一渠道失败不拖垮主流程。改 `src/services/image_stock_extractor.py` 的 `EXTRACT_PROMPT` 时 PR 描述附完整 prompt。
- 自动 tag 默认 opt-in：只有 commit title 含 `#patch` / `#minor` / `#major` 才触发版本号更新；手动 tag 必须 annotated。

## 8. Issue / PR / Skill 工作流

- issue 分析 / PR 审查 / issue 修复优先复用 `.claude/skills/` 下对应 skill，产物存 `.claude/reviews/`。
- PR 创建/更新、PR 审查、issue 分析前先同步基线：`git fetch --all --prune`；工作区干净且可 fast-forward 才 `git pull --ff-only`。否则不得 stash/reset/覆盖，改用已 fetch 的远端 refs，并在文档中记录基线差异。
- skill 默认基于 CI 证据开展；不得默认执行 `git pull/push/tag/gh pr create`，需用户确认。

PR 审查顺序：必要性 → 关联性 → 描述完整性（对照 `.github/PULL_REQUEST_TEMPLATE.md`）→ 验证证据 → 实现正确性 → 合入判定。标题建议 `<类型>: <修改内容>`（`fix/feat/refactor/docs/chore/test/ci`），不带工具/agent 前缀，仅作为协作提示不阻断。

合入阻断条件：正确性/安全性问题；阻断型 CI 未过；PR 描述与改动实质矛盾；缺回滚方案；反复契约漂移/补丁堆叠/验证证据失真。

### 8.1 Review 反馈处理

- 禁止只在 reviewer 点名位置追加补丁后声称"已全部修复"。
- 处理顺序：1) 列出原问题 → 2) 说明根因 → 3) 找出同一语义的所有相关路径（runtime/API/Web/CLI/诊断/docs/tests/workflows）→ 4) 修复完整契约 → 5) 补充覆盖反例的回归测试或说明无法验证原因 → 6) 同步更新 PR body 的 scope/验证/兼容/风险/回滚。
- CI 通过只证明自动检查，不能单独证明反例已闭合；无法收敛时主动说明需要拆分或关闭重做。

## 9. 交付与发布

- 默认交付结构：改了什么 / 为什么这么改 / 验证情况 / 未验证项 / 风险点 / 回滚方式。
- `docs` 任务可写 `docs only, tests not run`，但需说明已核对命令与文件名。
- 用户可见变更优先走 PR 合入，补齐 label 与验证说明。