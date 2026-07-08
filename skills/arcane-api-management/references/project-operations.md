# Project & Webhook Operations — Arcane

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
