---
name: deepsearch
description: >
  Use for 深度搜索/深度调研/多源核实/DeepSearch/deep research and for time-sensitive
  external facts that need citations from multiple sources. This installation routes the
  former DeepSearch workflow to the deployed GrokSearch HTTP gateway. Do not use for local
  codebase search, offline reasoning, or tasks where the user explicitly says not to search.
---

# DeepSearch — routed to deployed GrokSearch gateway

## 一句话描述

本 Skill 保留原 `deepsearch` 触发名，但默认调用已经部署在线上的 **GrokSearch HTTP gateway**，用来替换旧的本地 DeepSearch 工作流。GA 当前没有通用 MCP client，因此本接入是 **Skill + 包装脚本** 形态：agent 通过现有 `code_run` 调用脚本，脚本再请求线上 `/search`。

默认网关：`https://search.198707.xyz`

## 触发关键词

当用户消息包含以下需求时触发：
- “深度搜索” / “深度调研” / “多源核实” / “DeepSearch” / “deep research”
- 涉及时效信息、版本号、产品最新状态、外部事实验证
- 需要 ≥ 2 个独立来源交叉验证的复杂问题

不要触发：
- 本地代码库搜索、文件内容定位、纯代码编辑
- 用户明确说“不要联网/不要搜索”
- 简单常识或无需来源的离线推理

## 必需配置

优先级：

1. 临时覆盖：启动 GA 的 shell / launchd / 桌面桥进程环境变量。
2. 持久默认：GA 本地 keychain 条目 `groksearch_bearer_token`。

环境变量示例：

```bash
export GROKSEARCH_URL="https://search.198707.xyz"
export GROKSEARCH_BEARER_TOKEN="<线上网关 bearer token>"
```

兼容变量：`GROKSEARCH_TOKEN` 可替代 `GROKSEARCH_BEARER_TOKEN`。

若不用环境变量，可保存到 GA keychain：

```python
from keychain import keys
keys.set("groksearch_bearer_token", "<线上网关 bearer token>")
```

安全要求：
- 不要把真实 bearer token 写入 `SKILL.md`、脚本、`.env.example` 或 git。
- `/health` 不需要 token；`/search` 必须能从 env 或 keychain 取到 token。
- 如果返回 401，优先检查 env 覆盖值是否旧；其次检查 keychain 条目；必要时重启 GA/desktop bridge。

## Agent 调用方式

### 1. 健康检查

```bash
cd /Users/qing/code/GenericAgent
python3 skills/DeepSearch/scripts/groksearch_gateway.py --health
```

期望看到 JSON 内含 `status: ok`，HTTP 状态为 200。

### 2. 搜索

```bash
cd /Users/qing/code/GenericAgent
python3 skills/DeepSearch/scripts/groksearch_gateway.py "要搜索的问题" --timeout 180
```

或传原始 JSON：

```bash
python3 skills/DeepSearch/scripts/groksearch_gateway.py --json '{"query":"要搜索的问题","max_sources":5}' --timeout 180
```

脚本只使用 Python 标准库，不依赖旧 DeepSearch venv。

## 工作流程

1. 判断是否需要联网搜索。
   - 需要：用户明确要求、实时信息、版本号、外部状态、事实核验。
   - 不需要：本地仓库搜索、纯代码任务、用户拒绝联网。
2. 先运行健康检查；若 `/health` 失败，停止并报告网关不可用。
3. 运行搜索脚本；超时时把 `--timeout` 提高到 180 或 240 秒，最多重试一次。
4. 解析返回 JSON，提取 answer/content/findings/sources/citations 等字段。
5. 最终回答必须带引用；没有来源的关键事实不要断言。

## 证据标准（agent 必须遵守）

### 置信度标注

| 标签 | 判据 |
|------|------|
| **High** | ≥ 2 真正独立来源 + 官方/主流来源 + 时效符合 |
| **Medium** | ≥ 2 来源但权威性一般，或多源有可解释分歧 |
| **Low** | 单一来源、非权威来源、时效不明或结果不充分 |

### 引用规则

- 每个关键事实后带 `[标题](URL)` 引用。
- 严禁编造引用；没有 URL 的来源不能当作已验证引用。
- 末尾保留 `Sources:` 节，列出实际使用的 URL。
- 来源冲突时必须展示分歧，不要合并成单一结论。

### 来源质量

| 级别 | 包含 |
|------|------|
| **高** | 官方文档、GitHub、PyPI、arxiv、PEP/RFC、政府/标准机构 |
| **中** | Wikipedia、Stack Overflow、Reddit、Hacker News、主流媒体 |
| **低** | 无名个人博客、SEO 农场、AI 生成聚合站 |

仅有单一来源时，显式标注 `置信度: Low`。

## 常见故障

- `GROKSEARCH_BEARER_TOKEN is required`：GA 进程环境缺少 token；设置后重启 GA/desktop bridge。
- `HTTPError 401`：token 不匹配或线上容器仍使用旧 env；确认线上 `.env` 后 redeploy。
- `HTTPError 503`：后端搜索依赖暂不可用；稍后重试并保留错误 JSON。
- `timeout`：搜索耗时较长；用 `--timeout 180` 或 `--timeout 240` 重试一次。

## 输出格式建议

```markdown
结论：...

关键发现：
1. ... [来源标题](https://...)
2. ... [来源标题](https://...)

置信度：High|Medium|Low

Sources:
- [来源标题](https://...)
```

## 自检清单

- [ ] 搜索脚本实际运行过，而不是凭记忆回答
- [ ] 每个关键事实至少有 1 个真实 URL 引用
- [ ] 单源结论标了 `置信度: Low`
- [ ] 有分歧的来源已说明分歧
- [ ] 没泄露 bearer token

---

*DeepSearch compatibility skill — powered by deployed GrokSearch gateway.*
