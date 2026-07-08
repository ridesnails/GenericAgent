---
name: arcane-api-management
description: >
  Use when the user asks to manage Arcane (dc.ormz.pro) Docker environments via API —
  read-only inspection, project/container operations, GitOps/repo/webhook automation,
  multi-env management, and pre/post-change verification. Trigger for "Arcane/GitOps/
  API key/Docker 管理/项目重启/部署/巡检". Do not use for direct SSH docker-compose when
  Arcane API is available; do not read or print secrets.
---

# Arcane API Management Skill

## Task Routing

| User asks | Read | Do |
|---|---|---|
| inspect state / list projects / containers | `references/discovery.md` | run read-only GET, record ENV_ID |
| create/update/delete project or webhook | `references/project-operations.md` | confirm target id → mutate → verify |
| GitOps / git repo sync | `references/gitops.md` | list existing syncs first, autoSync=false on create |
| auth / API key / curl templates | `references/auth-and-api.md` | set ARCANE_API_KEY in env, never print |
| error / 401 / 404 / duplicate project | `references/gotchas.md` | stop blind retries, re-fetch OpenAPI |

## 核心原则

1. **优先 API，少用 UI**：Arcane 暴露 `/api/openapi.json`，认证支持 `X-API-Key` 和 Bearer JWT。日常管理优先 `curl`/脚本；UI 只用于最终确认或 API 不足时补充。
2. **只读先行**：任何变更前先抓取环境列表、目标项目/容器 runtime、GitOps sync、相关仓库状态。
3. **双重核验**：变更后至少用 API 核验一次；高风险操作再 UI 二次核验。
4. **破坏性操作必须询问用户**：`destroy`、`down`、删除容器/卷/仓库/API key、恢复卷备份、prune 等先确认。
5. **不要读取或输出 secret**：`.env`、API key、GitHub token、SSH key 只引用路径或环境变量，不打印内容。

## 已验证实例约定

- Arcane URL：`https://dc.ormz.pro`
- OpenAPI：`https://dc.ormz.pro/api/openapi.json`
- API-Key header：`X-API-Key: $ARCANE_API_KEY`
- 已知坑点：对已有同名项目创建 GitOps sync **不等于接管旧项目**，可能生成重复项目目录（如 `aione-1`）；Git 仓库没有真实 `.env` 时变量展开为空。详见 `references/gitops.md`。

## 最简 API 调用入口

详见 `references/auth-and-api.md`，核心要点：
```bash
export ARCANE_URL='https://dc.ormz.pro'
export ARCANE_API_KEY='...'   # 不要写入仓库/记忆/日志
curl -fsS -H "X-API-Key: ${ARCANE_API_KEY}" "${ARCANE_URL}/api/environments?limit=100"
```

## 变更前后核验清单

### 变更前
- [ ] API key 只在环境变量/密钥管理中使用
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

## 已知坑（完整版见 `references/gotchas.md`）

| 症状 | 处理 |
|---|---|
| 401/403 | 检查 `X-API-Key` 是否存在/过期/权限不足；不打印 key |
| 404 | 确认路径是否需要 `/api` 前缀；以实例 OpenAPI 和浏览器 network 为准 |
| GitOps 创建重复项目 | 立即停止自动同步、重命名重复项；不要先 down/destroy |
| compose 里变量为空 | 检查 `.env` 是否在服务器项目目录存在；仓库通常只放 `.env.example` |
| UI 与 API 不一致 | 刷新 UI；若仍不一致以 API/runtime 为主并说明缓存可能性 |
| 操作失败 2 次 | 重新抓 OpenAPI/schema/服务日志；不要无信息重试 |
