# Git Repos & GitOps — Arcane

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
