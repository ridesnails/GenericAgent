# GenericAgent `skills/` 目录完整盘点报告

> 分析范围：`/Users/qing/code/GenericAgent/skills`
> 分析时间：2026-06-23
> 分析师：skill-analyst（team-1782220712009）

---

## 一、执行摘要（TL;DR）

你的 `skills/` 目录里共有 **7 个技能**，按功能可粗分为：

| 功能域 | 技能 |
|---|---|
| 搜索/信息获取 | `AI-Search-Hub`, `DeepSearch` |
| 数据归档/导出 | `conversation_html_exporter`, `Web-Clipper-Conversation-Archive` |
| API/运维管理 | `arcane-api-management` |
| 逆向工程 | `js-reverse` |
| 音频/本地 LLM | `meeting-audio-local-workflow` |

**核心结论：**

1. **数量本身不算夸张** — 7 个技能覆盖了搜索、归档、运维、逆向、音频 5 个不同领域，每个都有明确触发条件，属于“按需唤起”的 Agent skill 模式。
2. **真正的体积炸弹是 `AI-Search-Hub`**：目录占 **~749 MB**（占整个 `skills/` 的 99% 以上），但其中 **747 MB 都是运行时脏数据**（`.venv`、`.git`、Chrome debug profile、历史输出 `out/`），真正源代码+文档只有约 **2 MB / 16,500 行**。
3. **第三方 vs 自研比例约 1:6**：`AI-Search-Hub` 是外部开源仓库（`minsight-ai-info/AI-Search-Hub`）作为 gitlink 引入；其余 6 个都是针对你自己的项目/基础设施自写的。
4. **语言极度统一**：几乎全是 Python + Markdown 文档 + 少量 Shell，没有多语言乱炖。
5. **臃肿等级：轻度功能臃肿，重度磁盘臃肿**。功能上属于正常垂直分化，但 `AI-Search-Hub` 里的 `.venv`、profile、输出目录严重污染仓库体积。

---

## 二、逐个技能目录清单

### 1. AI-Search-Hub

| 指标 | 数值 |
|---|---|
| 目录 | `skills/AI-Search-Hub/` |
| 总文件数 | 8,366 |
| 总大小 | **749.15 MB** |
| 去脏后文件数 | 19 |
| 去脏后大小 | **2,054 KB（≈2 MB）** |
| 主要脏数据 | `.venv`（Python 虚拟环境）、`.git`、 `chrome_debug_profile_skill/`、 `out/` |
| Python 代码行数 | ~2,900 行（10 个 `.py` 文件） |
| 文档行数 | ~1,800 行（README ×2 + SKILL.md + ROUTING.md） |
| 来源 | **第三方开源**（GitHub: `minsight-ai-info/AI-Search-Hub`） |

**核心文件：**

- `SKILL.md`（101 行）— skill 元信息与入口说明
- `README.md` / `README.en.md`（422 + 412 行）— 中英双语项目 README
- `ROUTING.md`（234 行）— 按问题类型/URL 域名选择搜索平台的决策文档
- `scripts/run_web_chat.py`（783 行）— 统一入口，负责 CDP 浏览器启动、登录检测、分发
- `scripts/site_chat_core.py`（952 行）— 通用 Playwright 聊天核心
- `scripts/doubao_playwright.py`（560 行）、`longcat_playwright.py`（504 行）、`yuanbao_playwright.py`（458 行）— 字节/美团/腾讯系站点脚本
- `scripts/qwen_playwright.py`、`grok_playwright.py`、`gemini_playwright.py`、`kimi_playwright.py`、`minimaxi_playwright.py`（各 5 行）— 仅 import 核心并调用
- `agents/openai.yaml`（7 行）— Agent 配置
- `docs/images/*.png`（3 张，约 7 MB）— 运行截图

**功能：** 通过 Playwright + Chrome DevTools 自动化 7 个 AI 搜索平台（元宝、LongCat、豆包、通义、Gemini、Grok、MiniMax / Kimi），按问题领域路由，自动处理登录态。

**第三方证据：** 该目录自带 `.git`，remote 指向 `minsight-ai-info/AI-Search-Hub.git`；在 `GenericAgent` 中以 `160000` gitlink 形式记录，父仓库 `.gitmodules` 不存在（属于裸 gitlink）。

---

### 2. DeepSearch

| 指标 | 数值 |
|---|---|
| 目录 | `skills/DeepSearch/` |
| 总文件数 | 18 |
| 去脏后文件数 | 10 |
| 去脏后大小 | **86 KB** |
| Python 代码行数 | ~1,050 行 |
| 文档行数 | **1,585 行**（`DeepSearch_SOP.md`） |
| 来源 | **自研** |

**核心文件：**

- `DeepSearch_SOP.md`（1,585 行）— 完整的深度搜索 SOP，含证据标准、搜索方法论、引用格式
- `scripts/search_planning.py`（207 行）— 复杂问题拆计划
- `scripts/dual_search.py`（130 行）— Grok + Tavily 双源并行搜索
- `scripts/_http.py`（303 行）— 共享 HTTP 工具：连接池、key 轮转、SSE 解析、Tavily/FireCrawl/Grok 封装
- `scripts/_creds.py`（118 行）— `.env` 凭证解析
- `scripts/grok_search.py`（76 行）、`tavily_search.py`（72 行）、`web_fetch.py`（95 行）、`web_map.py`（58 行）— 单一工具脚本

**功能：** 纯 HTTP 高并发深度调研。Grok + Tavily 双源交叉，FireCrawl/Tavily 两级页面抓取，强制“≥2 独立来源”证据标准。

---

### 3. Web-Clipper-Conversation-Archive

| 指标 | 数值 |
|---|---|
| 目录 | `skills/Web-Clipper-Conversation-Archive/` |
| 文件数 | 1 |
| 大小 | **7.44 KB** |
| 文档行数 | 159 行 |
| 来源 | **自研** |

**核心文件：**

- `SKILL.md`（159 行）— 说明如何通过 `clip.yi.uy` 的 Web Clipper Worker 保存项目对话（URL 模式或 HTML 上传模式）

**功能：** 把 AI/Agent 项目对话归档到 Obsidian/FNS 工作流。

---

### 4. arcane-api-management

| 指标 | 数值 |
|---|---|
| 目录 | `skills/arcane-api-management/` |
| 文件数 | 2 |
| 大小 | **14.74 KB** |
| Python 代码行数 | 113 行 |
| 文档行数 | 309 行 |
| 来源 | **自研** |

**核心文件：**

- `SKILL.md`（309 行）— Arcane（Docker/GitOps 管理平台）API 使用规范、端点清单、安全流程
- `arcane_api.py`（113 行）— 小型 `curl` 替代脚本，自动处理 `/api` 前缀、HTML fallback 检测

**功能：** 用 Arcane OpenAPI 替代 UI 做 Docker/项目/GitOps/Webhook 管理。

---

### 5. conversation_html_exporter

| 指标 | 数值 |
|---|---|
| 目录 | `skills/conversation_html_exporter/` |
| 总文件数 | 7（含 out/ 示例） |
| 去脏后文件数 | 4 |
| 去脏后大小 | **27.96 KB** |
| Python 代码行数 | 250 行 |
| 文档行数 | 46 行 |
| 来源 | **自研** |

**核心文件：**

- `exporter.py`（250 行）— 把 JSON/Markdown/文本对话转成精美单文件 HTML
- `SKILL.md`（46 行）— 使用说明
- `examples/*.json` — 示例输入

**功能：** 对话导出+美化，支持密文脱敏、代码高亮、搜索、角色过滤、折叠、打印样式、WebClipper 上传。

---

### 6. js-reverse

| 指标 | 数值 |
|---|---|
| 目录 | `skills/js-reverse/` |
| 文件数 | 20 |
| 大小 | **33.10 KB** |
| 文档行数 | ~1,200 行（SKILL + references/） |
| 来源 | **自研** |

**核心文件：**

- `SKILL.md`（262 行）— JS 逆向六阶段工作流
- `references/`（14 个 md）— 工具目录、补环境、去混淆、任务模板、输出契约等
- `references/cases/`（3 个案例）— AST 去混淆、签名模板、window 蜜罐
- `references/schemas/`（2 个 JSON）— 任务输入 schema + 示例
- `agents/openai.yaml`（7 行）

**功能：** 前端 JS 逆向工程规范，配合 JSReverser-MCP + Chrome DevTools 做签名定位、Hook 采样、补环境、AST 去混淆、VMP 插桩。

---

### 7. meeting-audio-local-workflow

| 指标 | 数值 |
|---|---|
| 目录 | `skills/meeting-audio-local-workflow/` |
| 文件数 | 3 |
| 大小 | **12.94 KB** |
| Python 代码行数 | 118 行 |
| Shell 代码行数 | 105 行 |
| 文档行数 | 120 行 |
| 来源 | **自研** |

**核心文件：**

- `SKILL.md`（120 行）— 使用说明与故障处理
- `run_meeting_workflow.sh`（105 行）— 一键转写+纪要工作流
- `local_mlx_meeting_summarize.py`（118 行）— 用 MLX + Qwen2.5-7B 分块整理会议纪要

**功能：** 本地中文长会议录音处理：FunASR 转写 + MLX Qwen 摘要，适用于 Apple Silicon 离线环境。

---

## 三、按用途分类

```
搜索与信息获取（2 个）
├── AI-Search-Hub        浏览器驱动多平台 AI 原生搜索
└── DeepSearch           HTTP 双引擎深度搜索 + 证据约束

归档与导出（2 个）
├── conversation_html_exporter   对话 → 单文件 HTML
└── Web-Clipper-Conversation-Archive  对话 → Web Clipper/Obsidian

基础设施/运维（1 个）
└── arcane-api-management  Arcane Docker/GitOps API 管理

安全/逆向（1 个）
└── js-reverse            前端 JS 逆向工程规范

多媒体/本地 LLM（1 个）
└── meeting-audio-local-workflow  会议音频转写与纪要
```

---

## 四、文件大小与语言分布

### 4.1 总体磁盘占用

| 技能 | 原始大小 | 去脏大小 | 脏数据占比 |
|---|---|---|---|
| AI-Search-Hub | 749.15 MB | 2.05 MB | **99.7%** |
| DeepSearch | 0.13 MB | 86 KB | ~35% |
| Web-Clipper-Conversation-Archive | 0.01 MB | 7 KB | 0% |
| arcane-api-management | 0.01 MB | 15 KB | 0% |
| conversation_html_exporter | 0.11 MB | 28 KB | ~75%（out/ 示例 HTML） |
| js-reverse | 0.03 MB | 33 KB | 0% |
| meeting-audio-local-workflow | 0.01 MB | 13 KB | 0% |
| **合计** | **~749.5 MB** | **~2.2 MB** | **99.7%** |

### 4.2 代码行数分布（去脏后）

| 语言 | 文件数 | 行数 | 占比 |
|---|---|---|---|
| Python | 22 | ~4,822 | 29% |
| Markdown | 24 | ~4,082 | 25% |
| JSON / YAML | 7 | ~408 | 2% |
| Shell | 1 | 105 | 1% |
| PNG 图片 | 3 | - | - |
| **总计** | **57** | **~16,583** | 100% |

> 注：行数包含注释和空行；Python 实际有效代码约 3,500–4,000 行。

### 4.3 依赖清单（通过 `import` 分析）

| 依赖 | 用途 | 涉及技能 |
|---|---|---|
| `playwright` | 浏览器自动化 | AI-Search-Hub |
| `requests` | HTTP 客户端 | DeepSearch, arcane-api-management |
| `mlx_lm` | Apple Silicon 本地 LLM | meeting-audio-local-workflow |
| `funasr` / `sensevoice` | ASR 转写 | meeting-audio-local-workflow（由外部脚本引用） |
| 标准库（`urllib`, `argparse`, `json`, `pathlib`…） | 通用 | 全部 |

**注意：** 没有 `requirements.txt`/`pyproject.toml` 等依赖声明文件，依赖散落在外部虚拟环境（`.venv_funasr`、`.venv_mlx`、`.venv`）和文档说明里。

---

## 五、第三方 vs 自研识别

| 技能 | 来源 | 判断依据 |
|---|---|---|
| **AI-Search-Hub** | **第三方/外部 bundled** | 自带 `.git`，remote=`minsight-ai-info/AI-Search-Hub.git`；父仓库以 `160000` gitlink 记录；README 有 GitHub badge 与商业产品广告 |
| DeepSearch | 自研 | 无 `.git`，直接由父仓库 `git ls-files` 追踪；代码风格与项目其他脚本一致；引用 `.env` 结构与 GenericAgent 根目录一致 |
| Web-Clipper-Conversation-Archive | 自研 | 同上；引用用户自己的 `clip.yi.uy` 部署 |
| arcane-api-management | 自研 | 同上；引用用户自己的 `dc.ormz.pro` 实例 |
| conversation_html_exporter | 自研 | 同上；引用 `../memory/keychain.py` 等内部路径 |
| js-reverse | 自研 | 同上；大量 GA/GenericAgent 内部术语 |
| meeting-audio-local-workflow | 自研 | 同上；引用 `/Users/qing/code/GenericAgent/.venv_*` 路径 |

**结论：1 个第三方 + 6 个自研。**

---

## 六、臃肿度评估

### 6.1 功能层面

| 维度 | 评分 | 说明 |
|---|---|---|
| 功能重叠 | 低 | 搜索有“浏览器 AI 搜索”和“HTTP 深度搜索”两条互补路径；归档有 HTML 导出和 Web Clipper 两条路径，用途不同 |
| 触发条件清晰度 | 高 | 每个 SKILL.md 都有明确的 `description` 和触发关键词 |
| 文档/代码比 | 高 | 整体文档行数与代码行数接近 1:1，SOP 驱动 |
| 可维护性 | 中 | 依赖无集中声明；AI-Search-Hub 是外部仓库，升级/分叉需谨慎 |

### 6.2 磁盘层面

| 维度 | 评分 | 说明 |
|---|---|---|
| 仓库体积 | **极高** | `skills/` 占 749 MB，其中 747 MB 是可排除的脏数据 |
| 脏数据类型 | 严重 | `.venv`、Chrome profile、`out/`、`.git` 都应进 `.gitignore` 或用外部路径 |
| 清理收益 | 极大 | 仅清理 AI-Search-Hub 的 `.venv`、profile、out 即可释放 700+ MB |

### 6.3 综合臃肿等级

**功能臃肿：🟡 轻度** — 7 个技能覆盖 5 个不同领域，每个都有明确边界，不算过度堆积。  
**磁盘臃肿：🔴 严重** — 99% 以上体积是运行时产物，严重污染 Git 仓库和备份。

---

## 七、发现的问题与建议

### 问题 1：AI-Search-Hub 的 gitlink 没有 `.gitmodules`

- 风险：其他机器克隆 `GenericAgent` 时不会自动拉取 `AI-Search-Hub` 子目录内容；父仓库只记录一个 commit hash。
- 建议：要么补 `.gitmodules` 走正式 submodule，要么把 AI-Search-Hub 的内容 flatten 进父仓库（如果你做了定制修改）。

### 问题 2：运行时目录进入版本控制

- `AI-Search-Hub/.venv/`、`.git/`、`chrome_debug_profile_skill/`、`out/` 合计约 747 MB。
- `conversation_html_exporter/out/` 也有生成文件。
- 建议：
  - 把这些路径加入 `.gitignore`
  - 已经进 Git 历史的需要 `git filter-repo` 或 BFG 清理，否则体积不会下降
  - `.venv` 建议用 `requirements.txt` 描述，由用户本地重建

### 问题 3：没有统一依赖声明

- 各 skill 依赖 Playwright、requests、mlx_lm、funasr 等，但 skill 目录内没有 `requirements.txt`/`pyproject.toml`。
- 建议：每个 skill 增加 `requirements.txt` 或项目根目录增加 `skills/requirements.txt` 分组说明。

### 问题 4：AI-Search-Hub 与 DeepSearch 的路由可能冲突

- 两者都处理“搜索”。
- 但触发条件已区分：`DeepSearch` 仅用于“深入搜索 / 多源交叉核实”关键词；`AI-Search-Hub` 用于指定平台/中国平台数据。
- 建议：在顶层 Agent 路由中保留这一优先级，避免同时唤起两者。

### 问题 5：Web-Clipper 技能无代码实现

- 只有 `SKILL.md`（159 行纯文档），没有可执行脚本。
- 建议：如果需要自动化，可复用 `conversation_html_exporter/exporter.py` 的 HTML 生成 + 上传能力，避免重复造轮子。

---

## 八、为什么看起来“这么多 skills”

一句话：**不是技能数量过多，而是 `AI-Search-Hub` 一个第三方仓库把磁盘体积和目录深度撑得很大，造成视觉上的“膨胀”。**

- 7 个技能对应 5 个不同能力域，是 Agent 架构下正常的垂直拆分。
- 自研的 6 个技能加起来只有 **~170 KB / 10,000 行**（代码+文档），非常精简。
- 真正“多”的是 `AI-Search-Hub` 里的平台适配脚本：它为 7 个 AI 搜索网站各写了 Playwright 脚本，加上路由文档和截图，显得目录很深。

如果你希望“瘦身”，优先做两件事：
1. **清理 `AI-Search-Hub` 的运行时脏数据**（释放 700+ MB）。
2. **把 AI-Search-Hub 改为正式 submodule 或 flatten**，避免 gitlink 裸奔。

---

*报告结束。*
