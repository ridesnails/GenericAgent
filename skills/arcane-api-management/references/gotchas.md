# Known Gotchas & Troubleshooting — Arcane

## 失败处理

| 症状 | 处理 |
|---|---|
| 401/403 | 检查 `X-API-Key` 是否存在、过期、权限不足；不要打印 key |
| 404 | 确认路径是否需要 `/api` 前缀；以实例 OpenAPI 和浏览器 network 为准 |
| GitOps 创建重复项目 | 立即停止自动同步、重命名重复项；不要先 down/destroy |
| compose 里变量为空 | 检查 `.env` 是否在服务器项目目录存在；Git 仓库通常只放 `.env.example` |
| UI 与 API 不一致 | 刷新 UI；若仍不一致，以 API/runtime 为主并说明缓存可能性 |
| 操作失败 2 次 | 重新抓 OpenAPI/schema/服务日志；不要无信息重试 |
