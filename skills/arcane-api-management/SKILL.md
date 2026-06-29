---
name: arcane-api-management
description: 用 Arcane 官方 OpenAPI/API-Key 管理 Docker 环境，适用于替代慢速 UI 的只读巡检、项目/容器操作、GitOps/仓库/Webhook 自动化、多环境管理与变更前后核验。触发：Arcane、dc.ormz.pro、GitOps、API key、Docker 管理、项目重启/部署/巡检。
---

# Arcane API Management Skill

## 核心原则

1. **优先 API，少用 UI**：Arcane 实例暴露 `/api/openapi.json`，OpenAPI `servers[0].url` 通常是 `${ARCANE_URL}/api`；认证支持 `X-API-Key` 和 Bearer JWT。日常管理优先 `curl`/脚本调用 API；UI 只用于最终人工确认或 API 不足时补充。
2. **只读先行**：任何变更前先抓取：环境列表、目标项目/容器 runtime、GitOps sync、相关仓库/文件状态。
3. **双重核验**：变更后至少用 API 核验一次；高风险操作再用 UI/页面二次核验。
4. **破坏性操作必须询问用户**：`destroy`、`down`、删除容器/卷/仓库/API key、恢复卷备份、prune 等要先确认。
5. **不要读取或输出 secret**：`.env`、API key、GitHub token、SSH key 只引用路径或环境变量，不打印内容。

## 已验证实例约定

- Arcane URL：`https://dc.ormz.pro`
- OpenAPI：`https://dc.ormz.pro/api/openapi.json`
- API-Key header：`X-API-Key: $ARCANE_API_KEY`
- 当前已知 GitOps 坑点：对已有同名项目创建 GitOps sync **不等于接管旧项目**，可能生成重复项目目录（如 `aione-1`），且 Git 仓库没有真实 `.env` 时变量会展开为空。

## 最简 API 调用模板

```bash
export ARCANE_URL='https://dc.ormz.pro'
export ARCANE_API_KEY='...'   # 不要写入仓库/记忆/日志

arcane_get() {
  curl -fsS -H "X-API-Key: ${ARCANE_API_KEY}" \
    "${ARCANE_URL}$1"
}

arcane_json() {
  method="$1"; path="$2"; body="$3"
  curl -fsS -X "$method" \
    -H "X-API-Key: ${ARCANE_API_KEY}" \
    -H 'Content-Type: application/json' \
    --data "$body" \
    "${ARCANE_URL}${path}"
}
```

Python 推荐模板：

```python
import os, requests
BASE = os.environ.get('ARCANE_URL', 'https://dc.ormz.pro').rstrip('/')
KEY = os.environ['ARCANE_API_KEY']
S = requests.Session()
S.headers.update({'X-API-Key': KEY})

def api(method, path, **kw):
    r = S.request(method, BASE + path, timeout=30, **kw)
    r.raise_for_status()
    if r.content:
        return r.json()
    return None
```

## 认证与 API-Key 管理

OpenAPI securitySchemes：

- `ApiKeyAuth`: header `X-API-Key`
- `BearerAuth`: JWT Bearer

端点：

- `GET /api-keys`：列出 API keys（管理员视角）
- `POST /api-keys`：创建 API key
- `GET /api-keys/{id}`、`PUT /api-keys/{id}`、`DELETE /api-keys/{id}`
- `GET /auth/me/api-keys`：列出当前用户自己的 key
- `POST /auth/me/api-keys`：创建自己的 key
- `DELETE /auth/me/api-keys/{id}`

创建 body schema 关键字段：

```json
{
  "name": "agent-arcane-management",
  "description": "API key for automation",
  "expiresAt": "2026-12-31T00:00:00Z",
  "permissions": [
    {"resource": "...", "action": "..."}
  ]
}
```

注意：`permissions` 不能超过创建者权限；具体 permission manifest 可从 OpenAPI/权限端点获取后再填，不要猜。

## 常用发现流程

### 1. 发现环境

```bash
arcane_get '/api/environments?limit=100'
```

若响应路径实际不带 `/api` 前缀，使用：

```bash
arcane_get '/environments?limit=100'
```

> 备注：Arcane 前端通常在 `/api/...` 反代；OpenAPI paths 内部常显示 `/environments`。实际调用以实例验证为准。

### 2. 找项目

```bash
ENV_ID='<environmentId>'
arcane_get "/api/environments/${ENV_ID}/projects?limit=100"
arcane_get "/api/environments/${ENV_ID}/projects/counts"
```

### 3. 项目详情与 compose/runtime

```bash
PROJECT_ID='<projectId>'
arcane_get "/api/environments/${ENV_ID}/projects/${PROJECT_ID}"
arcane_get "/api/environments/${ENV_ID}/projects/${PROJECT_ID}/compose"
arcane_get "/api/environments/${ENV_ID}/projects/${PROJECT_ID}/runtime"
arcane_get "/api/environments/${ENV_ID}/projects/${PROJECT_ID}/files"
```

用于确认：

- 项目名、目录、状态
- compose 是否有变量展开为空，例如 `Host(\`\`)`
- runtime 里实际容器 ID、服务数、健康状态
- GitOps 重名项目是否引用同一批旧容器 ID

### 4. 容器巡检

```bash
arcane_get "/api/environments/${ENV_ID}/containers?limit=100"
arcane_get "/api/environments/${ENV_ID}/containers/counts"
arcane_get "/api/environments/${ENV_ID}/containers/${CONTAINER_ID}"
```

低风险动作：`restart`、`start`、`stop` 也可能影响服务，执行前需确认目标和窗口：

```bash
curl -fsS -X POST -H "X-API-Key: $ARCANE_API_KEY" \
  "${ARCANE_URL}/api/environments/${ENV_ID}/containers/${CONTAINER_ID}/restart"
```

## 项目操作端点

- `GET /environments/{id}/projects`
- `POST /environments/{id}/projects`
- `GET /environments/{id}/projects/{projectId}`
- `PUT /environments/{id}/projects/{projectId}`
- `GET /environments/{id}/projects/{projectId}/compose`
- `GET /environments/{id}/projects/{projectId}/runtime`
- `GET /environments/{id}/projects/{projectId}/files`
- `GET /environments/{id}/projects/{projectId}/file`
- `POST /environments/{id}/projects/{projectId}/up`
- `POST /environments/{id}/projects/{projectId}/down` ⚠️ 高风险
- `POST /environments/{id}/projects/{projectId}/restart`
- `POST /environments/{id}/projects/{projectId}/redeploy`
- `POST /environments/{id}/projects/{projectId}/pull`
- `POST /environments/{id}/projects/{projectId}/build`
- `DELETE /environments/{id}/projects/{projectId}/destroy` ⚠️ 高风险
- `POST /environments/{id}/projects/{projectId}/archive` ⚠️ 先确认影响
- `POST /environments/{id}/projects/{projectId}/unarchive`

## Git 仓库与 GitOps

### Git repositories

- `GET /customize/git-repositories?limit=100`
- `POST /customize/git-repositories`
- `GET /customize/git-repositories/{id}`
- `PUT /customize/git-repositories/{id}`
- `DELETE /customize/git-repositories/{id}` ⚠️
- `GET /customize/git-repositories/{id}/branches`
- `GET /customize/git-repositories/{id}/files`
- `POST /customize/git-repositories/{id}/test`

Create body：

```json
{
  "name": "infra-compose",
  "url": "git@github.com:USER/infra-compose.git",
  "authType": "ssh",
  "sshKey": "...",
  "sshHostKeyVerification": "...",
  "enabled": true
}
```

也支持 `token`/`username` 字段；涉及凭据时只让用户在 UI/安全通道填，或用环境变量注入，不落盘。

### GitOps sync

常用：

- `GET /environments/{environmentId}/gitops-syncs?limit=100`
- `POST /environments/{environmentId}/gitops-syncs`
- `GET /environments/{environmentId}/gitops-syncs/{syncId}`
- `PUT/PATCH /environments/{environmentId}/gitops-syncs/{syncId}`（以 OpenAPI 实例为准）
- `POST /environments/{environmentId}/gitops-syncs/{syncId}/sync`
- `DELETE /environments/{environmentId}/gitops-syncs/{syncId}` ⚠️

创建/更新字段以 schema 为准，已验证常见字段：

```json
{
  "name": "aione-gitops",
  "repositoryId": "...",
  "branch": "main",
  "composePath": "hosts/bwg/aione/compose.yaml",
  "projectName": "aione",
  "autoSync": false,
  "syncInterval": 300
}
```

### GitOps 安全流程

1. 列仓库：`GET /api/customize/git-repositories?limit=100`
2. 测仓库：`POST /api/customize/git-repositories/{id}/test`
3. 列分支/文件：`GET /branches`、`GET /files`
4. 列现有 sync：`GET /api/environments/{ENV}/gitops-syncs?limit=100`
5. 创建前查同名项目：`GET /api/environments/{ENV}/projects?limit=100`
6. 创建 GitOps 时默认 `autoSync=false`
7. 创建后立即查：sync 状态、项目列表、runtime、compose
8. 若出现重复同名/目录 `*-1`：**不要 down/destroy/archive**；先关闭该 sync 的 `autoSync`，把重复项目改名为 `*-DISABLED-duplicate`，API + UI 确认旧项目仍运行。

## Webhook 自动化

端点：

- `GET /environments/{id}/webhooks`
- `POST /environments/{id}/webhooks`
- `PATCH /environments/{id}/webhooks/{webhookId}`
- `DELETE /environments/{id}/webhooks/{webhookId}` ⚠️

Create schema：

```json
{
  "name": "deploy-aione-on-ci",
  "targetType": "project",
  "targetId": "<projectId>",
  "actionType": "redeploy"
}
```

`targetType` 支持：`container`、`project`、`updater`、`gitops`。

`actionType` 支持：`update`、`start`、`stop`、`restart`、`redeploy`、`up`、`down`、`run`、`sync`。

CI 示例思路：GitHub Actions 构建/推送镜像后调用 Arcane webhook 或 API：

```yaml
- name: Redeploy project in Arcane
  run: |
    curl -fsS -X POST \
      -H "X-API-Key: ${{ secrets.ARCANE_API_KEY }}" \
      "${{ secrets.ARCANE_URL }}/api/environments/${{ secrets.ARCANE_ENV_ID }}/projects/${{ secrets.ARCANE_PROJECT_ID }}/redeploy"
```

更推荐通过 Arcane webhook token（若创建返回 webhook URL/token），避免在 CI 暴露广权限 API key。

## 多环境/Agent 管理

Arcane 支持 server/agent 多环境管理。常用端点：

- `GET /environments`：列所有环境/agent
- `GET /environments/{id}/version`：版本
- `GET /environments/{id}/deployment`：agent/deployment 信息
- `GET /environments/{id}/deployment/mtls/bundle`：mTLS bundle（敏感，只引用不打印）
- `POST /environments/{id}/test`：环境连通性测试
- `GET /environments/{id}/events` 或 `/events/environment/{environmentId}`：事件流/历史

## 变更前后核验清单

### 变更前

- [ ] API key 是否只在环境变量/密钥管理中使用
- [ ] `GET /environments` 确认 ENV_ID
- [ ] `GET /projects` 按 name/id 双确认目标
- [ ] `GET /projects/{id}/runtime` 记录容器 ID、服务状态
- [ ] `GET /projects/{id}/compose` 检查变量是否为空
- [ ] GitOps 操作前列 `gitops-syncs`，确认没有重复 sync
- [ ] 高风险动作已向用户确认

### 变更后

- [ ] API 返回码/JSON 成功
- [ ] 再查项目 runtime：服务数、状态、容器 ID
- [ ] 再查容器列表/health
- [ ] GitOps 再查 sync：`autoSync`、`lastSyncStatus`、`lastSyncCommit`
- [ ] 必要时 UI 页面二次确认
- [ ] 记录新的已验证事实到 `arcane_gitops_sop.md` 或相关记忆

## 失败处理

| 症状 | 处理 |
|---|---|
| 401/403 | 检查 `X-API-Key` 是否存在、过期、权限不足；不要打印 key |
| 404 | 确认路径是否需要 `/api` 前缀；以实例 OpenAPI 和浏览器 network 为准 |
| GitOps 创建重复项目 | 立即停止自动同步、重命名重复项；不要先 down/destroy |
| compose 里变量为空 | 检查 `.env` 是否在服务器项目目录存在；Git 仓库通常只放 `.env.example` |
| UI 与 API 不一致 | 刷新 UI；若仍不一致，以 API/runtime 为主并说明缓存可能性 |
| 操作失败 2 次 | 重新抓 OpenAPI/schema/服务日志；不要无信息重试 |
