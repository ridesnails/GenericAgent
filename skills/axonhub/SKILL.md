---
name: axonhub
description: >
  Use when the user asks to manage an AxonHub AI-Gateway instance — check status,
  list/add/update channels or models, manage downstream LLM API keys. Trigger for
  "AxonHub/api.198707.xyz 渠道/模型/key 管理". Credentials are read from env vars or
  keychain and never printed. Do not use for generic LLM proxy configuration outside
  AxonHub.
---

# AxonHub 实例管理 Skill

用途：对已部署的 AxonHub AI-Gateway 实例做脚本化管理——查看状态、列渠道/模型、按真实 schema 增改渠道与模型、管理下游 LLM API key。凭证按「环境变量优先、本地 keychain 兜底」解析，**绝不打印**。

## 前置
- 默认实例：`https://api.198707.xyz`（v1.0.0-beta4，同一台 BWG；旧域名 `api.ormz.pro` 已废弃勿用）。如换实例，设环境变量 `AXONHUB_URL`。
- 脚本：`skills/axonhub/axonhub.py`（纯标准库，无第三方依赖）。
- 凭证解析顺序：先读环境变量，缺失再回退本地 keychain。三个凭证：
  | 用途 | 环境变量 | keychain 条目 |
  |---|---|---|
  | admin 账号（owner，scopes=`*`，全功能链路） | `AXONHUB_ADMIN_USER` / `AXONHUB_ADMIN_PASS` | `axonhub_admin_user` / `axonhub_admin_pass` |
  | service-account key（`ah-...`，仅下游 API key 生命周期） | `AXONHUB_SA_KEY` | `axonhub_service_account_key` |
- **可移植用法（codex / claude code / 任意主机）**：脚本纯标准库无依赖，复制 `axonhub.py` 后只需设环境变量即可，无需 keychain：
  ```bash
  export AXONHUB_URL=https://your-instance      # 可选，默认 api.198707.xyz
  export AXONHUB_ADMIN_USER=you@example.com
  export AXONHUB_ADMIN_PASS=...
  export AXONHUB_SA_KEY=ah-...                   # 只用 admin 链路时可省略
  python3 axonhub.py status
  ```
- **本机 GenericAgent 主机**：不设 env，自动从加密 keychain 取上述条目（路径默认 `GA_MEMORY_DIR` 或 `…/GenericAgent/memory`）。缺条目时用 `keys.set("name", file="/path/to/secret")` 补，先写文件再存，别命令行明文传。

## 两条链路（关键区别，别混用）
1. **admin 链路** `POST /admin/graphql`：渠道、模型、用户、系统状态全套。
   - 鉴权：先 `POST /admin/auth/signin {email,password}` 拿 JWT，再 `Authorization: Bearer <jwt>`。
   - 脚本自动登录并把 JWT 缓存到 `~/.axonhub_token`（mode 600，~50min），401 时自动重登。
2. **service 链路** `POST /openapi/v1/graphql`：只有下游 LLM API key 相关。
   - 鉴权：`Authorization: Bearer <ah-key>`。
   - 可用字段仅：`createLLMAPIKey` / `updateAPIKeyProfiles` / `loadApiKeyProfileTemplate`（mutation）+ `apiKeyQuotaUsages`（query）。
   - **想建渠道/模型/查状态，service key 无能为力，必须走 admin 链路。**

## 命令入口
```bash
cd /Users/qing/code/GenericAgent/skills/axonhub

# --- 只读（admin） ---
python axonhub.py status                 # 系统状态 + 版本
python axonhub.py dashboard              # 请求总数/失败数/平均响应/按日统计
python axonhub.py channels [--limit 100] # 渠道列表(id name type status baseURL defaultTestModel)
python axonhub.py models   [--limit 100] # 模型列表(id modelID name developer status group)

# --- 任意 admin GraphQL（增改渠道/模型走这里） ---
python axonhub.py graphql '<query/mutation>' '<json-variables>'

# --- service 链路 ---
python axonhub.py sa-graphql '<query/mutation>' '<json-variables>'
python axonhub.py create-key <name>          # 新建下游 LLM API key
python axonhub.py quota --key ah-...          # 或 --id <keyID>，查配额用量
```

## 真实 schema 要点（已 introspect 验证）
- `channels` / `models` 是 Relay Connection：`{ totalCount edges{ node{...} } }`，分页用 `first`/`after`。
- `systemVersion` / `dashboardOverview` 是对象，不是连接。
- `DashboardOverview` 字段：`totalRequests` `failedRequests` `averageResponseTime` `requestStats{date count}`。
- `ChannelStatus` 枚举：`enabled` / `disabled` / `archived`。
- `ChannelType`：58 种（openai/anthropic/gemini/deepseek/zai/minimax…）。
- 建渠道 `CreateChannelInput`：必填 `type! name! credentials{apiKey...} supportedModels! defaultTestModel!`（+可选 baseURL/tags/orderingWeight/…；`status` 不可用于 create）。
  - 注意：`supportedModels` 与 `defaultTestModel` 必填；UI 上“创建”按钮禁用多半是没选默认测试模型。
  - 新建渠道默认 `disabled`；启用/禁用必须走专用 `updateChannelStatus(id,status)`，不要用 `updateChannel(input:{status})`。
  - 公益/分组标签可用 `tags:["公益"]` 随 create/update 写入；写后必须回读确认。
- 建模型 `CreateModelInput`：必填 `developer! modelID! name! icon! group! modelCard! settings!`。
- 测渠道 `testChannelAPIKeys(channelID, modelID)`：返回 `total/successCount/failedCount/results{keyPrefix success latency error disabled}`；字段名以 introspection 为准，不要猜 `message/key/responseTime`。

### 增改示例（admin 链路）
```bash
# 新建一个渠道
python axonhub.py graphql 'mutation($i:CreateChannelInput!){ createChannel(input:$i){ id name status } }' \
  '{"i":{"type":"openai","name":"my-openai","credentials":{"apiKey":"sk-..."},"supportedModels":["gpt-4o"],"defaultTestModel":"gpt-4o"}}'

# 启用/禁用渠道（先 channels 拿到 id；状态必须用专用 mutation）
python axonhub.py graphql 'mutation($id:ID!,$status:ChannelStatus!){ updateChannelStatus(id:$id,status:$status){ id status } }' \
  '{"id":"gid://axonhub/Channel/12","status":"enabled"}'

# 测试渠道 key；如果默认模型失败，逐个 modelID 测，选一个成功模型设为 defaultTestModel
python axonhub.py graphql 'mutation($channelID:ID!,$modelID:String!){ testChannelAPIKeys(channelID:$channelID,modelID:$modelID){ total successCount failedCount results{ keyPrefix success latency error disabled } } }' \
  '{"channelID":"gid://axonhub/Channel/12","modelID":"gpt-4o"}'
```

## 安全约束
- 凭证只从 keychain 读，作为 header/body 使用，永不写日志、永不 print 原值。
- 只读命令默认安全；改状态的只有 `create-key` 和显式带 mutation 的 `graphql`/`sa-graphql`。
- 跑改写前先用对应只读命令确认目标对象的真实 id 与当前值。

## 验收 / 排障
- 改完渠道或模型后，**不能只看返回**：用 `channels`/`models`（或重查目标 id）回读确认持久化。改默认测试模型尤其要回读下拉真实值。
- 渠道启用后用 `testChannelAPIKeys` 实测；若默认测试模型因额度/限流/模型类型失败，逐个 `supportedModels` 测，选择至少一个 `successCount>0` 的文本模型作为 `defaultTestModel` 后再回读。
- service 链路若返回字段校验错误（非 401），说明 key 有效但查询字段不对——参考上面“可用字段仅 4 个”。
- 同时残留多个弹窗会读错字段（仅 Web UI 操作时）；脚本链路无此问题，优先用脚本。

## 相关维护 SOP
- 实例底层操作细节见 `axonhub_sop.md`（UI 保存异常时挂钩页面原 fetch 等）。
