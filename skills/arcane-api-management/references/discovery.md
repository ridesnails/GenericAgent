# Discovery & Multi-Env — Arcane

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


## 多环境/Agent 管理

Arcane 支持 server/agent 多环境管理。常用端点：

- `GET /environments`：列所有环境/agent
- `GET /environments/{id}/version`：版本
- `GET /environments/{id}/deployment`：agent/deployment 信息
- `GET /environments/{id}/deployment/mtls/bundle`：mTLS bundle（敏感，只引用不打印）
- `POST /environments/{id}/test`：环境连通性测试
- `GET /environments/{id}/events` 或 `/events/environment/{environmentId}`：事件流/历史
