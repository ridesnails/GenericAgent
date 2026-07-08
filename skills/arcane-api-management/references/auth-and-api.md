# Auth & API Templates — Arcane

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
