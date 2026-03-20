# 本机 Demo Step2: Vercel 对接检查 Runbook

本文档只面向执行：本机 backend 与 tunnel 已经就绪，但当前 Windows 主机暂时无法访问 `*.vercel.app:443`。等网络恢复后，按本文档顺序执行即可完成 Vercel 对接验证。

## 当前仓库检查结论

- `vercel.json` 构建根仍是仓库根目录。
- 前端构建输出目录是 `frontend/dist`。
- 前端所有 API 调用都走相对路径 `/api/*`，不依赖部署态 `VITE_API_BASE_URL`。
- 当前仓库已补上 Vercel API 代理函数：`api/[...path].js`
  - Vercel 侧通过该函数读取 `BACKEND_URL`
  - 代理目标为：`<BACKEND_URL>/api/*`
- `vercel.json` 当前只负责静态前端构建和 SPA rewrite，不再把 `${BACKEND_URL}` 直接写进 rewrite destination。

## BACKEND_URL 应填什么

`BACKEND_URL` 应填写 Cloudflare Quick Tunnel 的根地址：

```text
https://<your-quick-tunnel>.trycloudflare.com
```

要求：

- 必须带 `https://`
- 不要带末尾 `/`
- 不要带 `/api`

正确示例：

```text
https://blue-sky-demo.trycloudflare.com
```

错误示例：

```text
https://blue-sky-demo.trycloudflare.com/
https://blue-sky-demo.trycloudflare.com/api
```

## redeploy 后应验证哪些 URL

先验证 tunnel 直连：

- `<TUNNEL_BASE_URL>/api/health`
- `<TUNNEL_BASE_URL>/api/import/schema`
- `<TUNNEL_BASE_URL>/api/search`

再验证 Vercel 域名：

- `<VERCEL_BASE_URL>/api/health`
- `<VERCEL_BASE_URL>/api/import/schema`
- `<VERCEL_BASE_URL>/api/search`
- `<VERCEL_BASE_URL>/api/graph/discovery`

## 网络恢复后的执行顺序

1. 确认 Cloudflare Quick Tunnel 仍然可访问。
2. 先跑 tunnel 校验脚本，证明 backend 通过 tunnel 正常可达。
3. 在 Vercel Project Settings 中设置 `BACKEND_URL=<你的 tunnel 根地址>`。
4. 触发一次 redeploy。
5. redeploy 完成后，先访问 Vercel 首页确认静态站点可达。
6. 再跑 Vercel rewrite 校验脚本。
7. 如果 Vercel API 失败但 tunnel API 正常，优先检查 Vercel 环境变量和 redeploy 是否生效。

## 可直接执行的脚本

tunnel 直连验证：

```bash
TUNNEL_BASE_URL=https://<your-quick-tunnel>.trycloudflare.com \
bash /home/ray/kg-system/scripts/verify/check_tunnel_backend.sh
```

Vercel rewrite 验证：

```bash
VERCEL_BASE_URL=https://<your-project>.vercel.app \
bash /home/ray/kg-system/scripts/verify/check_vercel_rewrite.sh
```

如果你要显式指定空间头：

```bash
SPACE_NAME=demo_kg \
TUNNEL_BASE_URL=https://<your-quick-tunnel>.trycloudflare.com \
bash /home/ray/kg-system/scripts/verify/check_tunnel_backend.sh
```

```bash
SPACE_NAME=demo_kg \
VERCEL_BASE_URL=https://<your-project>.vercel.app \
bash /home/ray/kg-system/scripts/verify/check_vercel_rewrite.sh
```

## 最终验收命令

tunnel：

```bash
curl -fsS https://<your-quick-tunnel>.trycloudflare.com/api/health
curl -fsS https://<your-quick-tunnel>.trycloudflare.com/api/import/schema
curl -fsS -H 'Content-Type: application/json' \
  --data-raw '{"q":"ca","search_in_name":true,"search_in_description":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains","include_edges":false}' \
  https://<your-quick-tunnel>.trycloudflare.com/api/search
```

vercel：

```bash
curl -fsS https://<your-project>.vercel.app/api/health
curl -fsS https://<your-project>.vercel.app/api/import/schema
curl -fsS -H 'Content-Type: application/json' \
  --data-raw '{"q":"ca","search_in_name":true,"search_in_description":false,"entity_type":null,"source":null,"entity_raw_id":null,"entity_raw_id_mode":"contains","include_edges":false}' \
  https://<your-project>.vercel.app/api/search
curl -fsS -H 'Content-Type: application/json' \
  --data-raw '{"seed_vids":[1],"allowed_entity_types":[],"allowed_relation_types":[],"max_nodes":80,"max_edges":200,"top_k_per_type":10,"include_candidate_candidate_edges":true,"include_seed_seed_edges":false,"hop":1}' \
  https://<your-project>.vercel.app/api/graph/discovery
```
