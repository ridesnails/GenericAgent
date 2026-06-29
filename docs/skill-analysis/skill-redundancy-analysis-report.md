# GenericAgent `skills/` 冗余与膨胀分析报告

## 1. 执行摘要

当前 `GenericAgent/skills/` 下共有 **7 个 skill**。数量本身不算多，但存在明显的**重复造轮子、架构不统一、文档型 skill 偏多**的问题。用户的"为什么这么多 skills"抱怨是有道理的：部分 skill 功能可合并，部分 skill 内部代码高度重复，且缺少跨 skill 的公共工具库。

| 维度 | 评估 |
|------|------|
| Skill 数量 | 7 个，处于可接受范围，但质量参差 |
| 重复程度 | **高** — 浏览器/CDP/HTTP/凭证加载/文本清洗等逻辑多处重复 |
| 架构一致性 | **低** — 有的 skill 是文档，有的是单脚本，有的是完整脚本包 |
| 可维护性 | **中低** — 修改一处通用逻辑需要改多个文件 |
| 推荐方向 | 提取公共库、合并同类 skill、重构 AI-Search-Hub 遗留脚本 |

---

## 2. 各 Skill 功能速览

| Skill | 核心功能 | 实现形态 | 体量（行数） |
|-------|---------|---------|------------|
| `AI-Search-Hub` | 浏览器自动化访问国内外 AI 搜索平台（元宝/LongCat/豆包/通义/Gemini/Grok/MiniMax/Kimi） | Python + Playwright，8 个脚本 + 2 个 markdown | ~3,700 行有效代码 |
| `DeepSearch` | HTTP 双引擎深度搜索：Grok + Tavily + FireCrawl，带搜索规划与证据标准 | Python + requests，6 个工具脚本 + 1 个 SOP | ~960 行代码 + 1,585 行文档 |
| `Web-Clipper-Conversation-Archive` | 通过 `clip.yi.uy` 保存对话/会话记录 | **仅 SKILL.md**，无代码 | 160 行文档 |
| `arcane-api-management` | 通过 API 管理 Arcane Docker/GitOps 实例 | 单 Python helper + SKILL.md | 114 行代码 |
| `conversation_html_exporter` | 将对话导出为自包含 HTML，可选上传 WebClipper | 单 Python 脚本 | 250 行代码 |
| `js-reverse` | JS 逆向工程规范（签名/补环境/Hook/去混淆） | **仅文档/reference + agents/openai.yaml**，无执行代码 | 262 行文档 |
| `meeting-audio-local-workflow` | 本地 FunASR + MLX/Qwen 会议录音转写与纪要 | 1 Python + 1 Shell | 223 行代码 |

> 注：`.git/`、`.venv/`、`chrome_debug_profile_skill/`、`out/`、`examples/` 等运行时/缓存目录不计入。

---

## 3. 重叠与重复分析

### 3.1 搜索类重叠：`AI-Search-Hub` vs `DeepSearch`

两者都叫"搜索"，但实现路径不同：

| | `AI-Search-Hub` | `DeepSearch` |
|---|---|---|
| 入口 | 浏览器自动化（Playwright + CDP） | HTTP API（requests） |
| 数据源 | 各平台原生聊天界面 | Grok API + Tavily + FireCrawl |
| 适用场景 | 需要平台生态数据（公众号/抖音/X） | 深度研究、交叉验证、证据链 |
| 共同点 | 都查询 Grok；都返回文本/引用；都有路由/规划思想 | |

**结论**：目标用户场景不同，**不建议直接合并为一个 skill**，但应统一为"搜索能力层"，对外暴露两个模式：
- `search --mode browser`（原 AI-Search-Hub）
- `search --mode deep`（原 DeepSearch）

### 3.2 对话存档类重叠：`Web-Clipper-Conversation-Archive` vs `conversation_html_exporter`

- `conversation_html_exporter` 已内置 `--upload-webclipper` 功能，默认上传到 `https://c.yi.uy`。
- `Web-Clipper-Conversation-Archive` 只是描述如何调用 `clip.yi.uy` 的文档，**无独立代码**。

**结论**：`Web-Clipper-Conversation-Archive` 应被合并/降级为 `conversation_html_exporter` 的一个 workflow 章节，不再作为独立 skill。

### 3.3 代码级重复（AI-Search-Hub 内部最严重）

`AI-Search-Hub` 同时存在两套实现：

1. **新版通用 core**：`site_chat_core.py`（952 行），统一支持 qwen/gemini/grok/minimaxi/kimi。
2. **旧版独立脚本**：`yuanbao_playwright.py`（458 行）、`longcat_playwright.py`（504 行）、`doubao_playwright.py`（561 行），各自完整实现了一套浏览器交互逻辑。

重复出现的函数/逻辑：

| 函数/逻辑 | 出现位置 | 建议 |
|-----------|---------|------|
| `first_visible` | `site_chat_core.py`, `doubao_playwright.py`, `longcat_playwright.py`, `yuanbao_playwright.py` | 统一到 `site_chat_core` |
| `any_visible` | `site_chat_core.py`, `run_web_chat.py`, `doubao_playwright.py` | 统一 |
| `candidate_texts` / 文本清洗 | 同上 | 统一 |
| `latest_new_text` | `site_chat_core.py`, `doubao_playwright.py` | 统一 |
| `fill_question` / DOM 填充 | `site_chat_core.py`, `doubao_playwright.py` | 统一 |
| `open_automation_page` / `open_dedicated_page` | `site_chat_core.py`, `run_web_chat.py`, `doubao_playwright.py` | 统一 |
| `resolve_cdp_url` / CDP HTTP 转 WS | `site_chat_core.py`, `run_web_chat.py`, `doubao_playwright.py` | 统一 |
| `write_output` | 所有脚本 | 统一 |
| `STARTUP_PAGE_PREFIXES` 元组 | 至少 3 个文件 | 统一为常量 |
| 浏览器启动/profile 复制/lock 清理 | `run_web_chat.py` | 应抽为公共 browser 工具 |

**最突出的问题**：`doubao_playwright.py` 与 `site_chat_core.py` 大量代码几乎逐行重复，只是配置不同。按现有趋势，每新增一个平台就要复制一份脚本，维护成本会指数增长。

### 3.4 跨 Skill 公共能力缺失

| 能力 | 当前状态 | 重复次数 |
|------|---------|---------|
| HTTP session + key rotation | `DeepSearch/_http.py` 实现较好 | 其他 skill 各自用 `urllib`/`requests` 裸写 |
| 凭证加载（.env + env var） | `DeepSearch/_creds.py` 实现较好 | 各 skill 硬编码 key 名或依赖外部注入 |
| CDP / Playwright 浏览器管理 | `AI-Search-Hub` 内部分散 | 至少 3 个文件 |
| JSON stdout / UTF-8 处理 | `DeepSearch/_http.py` 的 `dump_json` | 各脚本自行 `json.dumps` |
| Secret redaction | `conversation_html_exporter/exporter.py` | 其他 skill 未做 |

`DeepSearch` 在 `_http.py` / `_creds.py` 上的设计是值得推广的；但它是 skill 内部模块，没有复用价值。

---

## 4. 疑似实验性 / 一次性 / 文档型 Skill

| Skill | 状态 | 建议 |
|-------|------|------|
| `Web-Clipper-Conversation-Archive` | 仅文档，且依赖外部服务 `clip.yi.uy`（文档中自述 TLS 探测失败） | **合并**到 `conversation_html_exporter`，或删除 |
| `js-reverse` | 仅规范文档 + reference，实际执行依赖外部 `JSReverser-MCP` | 若使用频率低，可改为 `docs/playbooks/js-reverse.md`，不作为 skill |
| `arcane-api-management` | 强绑定用户私有 Arcane 实例 `dc.ormz.pro` | 保留，但建议移到 `skills/infrastructure/` 或重命名为 `arcane-ops`，避免与通用 skill 并列 |
| `meeting-audio-local-workflow` | Apple Silicon + 本地模型专用，场景窄但完整 | 保留，可作为垂直 skill |
| `conversation_html_exporter` | 单文件小工具 | 保留，但合并 WebClipper 后更完整 |

---

## 5. Skill 数量是否合理？

**结论：数量 7 个可以接受，但"有效 skill"只有约 4-5 个。**

如果按"是否包含可执行代码 + 是否有独立场景"重新分类：

| 类别 | 当前 Skill | 合理数量 |
|------|-----------|---------|
| 搜索 | AI-Search-Hub, DeepSearch | **1 个统一 Search skill，2 个 mode** |
| 对话存档 | Web-Clipper, conversation_html_exporter | **1 个** |
| 基础设施运维 | arcane-api-management | 1 个 |
| 本地音频处理 | meeting-audio-local-workflow | 1 个 |
| JS 逆向规范 | js-reverse | **0 或 1（文档型）** |

理想情况下可收敛到 **4-5 个核心 skill + 1 个共享工具库**。

---

## 6. 具体重构建议

### 6.1 建立跨 Skill 公共库（优先级：高）

建议新增 `skills/_shared/` 或项目根目录 `shared/`：

```
shared/
  http.py          # session pool, key rotation, SSE/JSON parser, retry
  creds.py         # env/.env 统一凭证加载
  browser.py       # CDP 连接、Playwright 启动、profile 复制、lock 清理
  io.py            # JSON stdout, write_output, UTF-8 配置
  redaction.py     # secret redaction patterns
```

`DeepSearch/_http.py` 和 `_creds.py` 是很好的起点，可直接提升为公共模块。

### 6.2 重构 `AI-Search-Hub`（优先级：高）

1. 将所有平台统一接到 `site_chat_core.py`。
2. 删除/迁移 `doubao_playwright.py`、`longcat_playwright.py`、`yuanbao_playwright.py` 中的重复 helper，仅保留平台特有逻辑。
3. `run_web_chat.py` 只负责：参数解析 → 浏览器启动/复用 → 调用平台脚本。不要再包含 `any_visible`、`open_automation_page` 等 DOM 逻辑。
4. 将 `STARTUP_PAGE_PREFIXES`、CDP URL 解析、profile seeding 等移到 `shared/browser.py`。

目标形态：

```
skills/ai-search-hub/
  SKILL.md
  ROUTING.md
  scripts/
    run.py                    # 统一入口
    sites/
      yuanbao.py              # 仅平台配置/特殊步骤
      longcat.py
      doubao.py
      qwen.py                 # 可能只剩 5 行
      gemini.py
      grok.py
      minimaxi.py
      kimi.py
```

### 6.3 合并 `Web-Clipper-Conversation-Archive` 到 `conversation_html_exporter`（优先级：中）

- 将 `Web-Clipper-Conversation-Archive/SKILL.md` 的内容移到 `conversation_html_exporter/SKILL.md` 的"Archive Workflow"章节。
- `exporter.py` 的 `--upload-webclipper` 已覆盖主要功能，只需补全 cURL 模板和失败处理说明。
- 删除 `Web-Clipper-Conversation-Archive/` 目录。

### 6.4 统一搜索入口（优先级：中）

可选方案 A（推荐）：保留两个 skill，但在 SKILL.md 中明确分工：
- `AI-Search-Hub`：平台原生搜索、社交/生态数据。
- `DeepSearch`：深度研究、交叉验证、证据链。

可选方案 B（更激进）：合并为 `skills/search/`，提供：
- `search.py --engine browser --site qwen ...`
- `search.py --engine deep --query "..."`
- 共享 routing 决策（中文生态 → browser；深度研究 → deep）。

### 6.5 处理 `js-reverse`（优先级：低）

- 如果它是频繁触发的规范，保留为 skill，但应补充至少一个本地入口脚本（例如调用 MCP 的包装器）。
- 如果几乎不用，建议降级为 `docs/js-reverse-playbook.md`，从 skills 目录移出。

### 6.6 依赖管理（优先级：中）

当前 `pyproject.toml` 只有项目核心依赖，各 skill 的依赖（`playwright`、`requests`、`mlx-lm`、`pygments` 等）散落在 `.venv`、README 或口头说明中。建议：

- 在 `pyproject.toml` 增加 optional extras：
  ```toml
  [project.optional-dependencies]
  search = ["playwright", "requests"]
  deepsearch = ["requests"]
  meeting = ["mlx-lm", "funasr"]
  exporter = ["pygments"]
  ```
- 或每个 skill 下放 `requirements.txt`。

### 6.7 移除 Skill 内部的 `.git` 目录

`AI-Search-Hub` 内部包含 `.git`（疑似从独立仓库 vendor 进来），会增加认知负担。建议：
- 如果它是独立项目，用 git submodule 或 package 引用。
- 如果已内嵌，删除 `.git`，作为普通子目录管理。

---

## 7. 推荐行动计划

| 优先级 | 行动 | 预计影响 |
|--------|------|---------|
| P0 | 创建 `shared/` 公共库；迁移 `DeepSearch/_http.py`、`_creds.py` | 大幅减少后续重复代码 |
| P0 | 重构 `AI-Search-Hub`：legacy 脚本接入 `site_chat_core`，删除重复 helper | 维护性提升最大 |
| P1 | 合并 `Web-Clipper-Conversation-Archive` → `conversation_html_exporter` | 减少 1 个 skill |
| P1 | 为各 skill 声明依赖（extras 或 requirements.txt） | 可复现性提升 |
| P2 | 明确 `AI-Search-Hub` 与 `DeepSearch` 分工，或合并为统一 Search skill | 减少用户/Agent 选择困惑 |
| P2 | 评估 `js-reverse` 是否保留为 skill | 可能减少 1 个 skill |
| P3 | 移除 skill 内部 `.git` 目录，统一项目结构 | 仓库整洁 |

---

## 8. 总结

"skills 太多"的根本问题不是数量，而是：

1. **同一类能力被拆成多个 skill**（搜索、存档）。
2. **单个 skill 内部代码高度重复**（AI-Search-Hub 新旧两套实现并存）。
3. **缺少跨 skill 公共工具库**，导致每个 skill 都要重复实现 HTTP、凭证、浏览器管理。
4. **部分 skill 只是文档**，没有可执行价值。

按本报告重构后，预计可以从 7 个 skill 收敛到 **4-5 个核心 skill + 1 个共享库**，同时显著降低维护成本。
