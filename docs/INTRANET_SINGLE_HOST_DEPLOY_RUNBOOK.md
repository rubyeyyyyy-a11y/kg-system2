# KG System 内网单机验证环境部署 Runbook

本文档是当前仓库唯一的内网验证环境部署标准。目标是让仓库在 Ubuntu 24.04 单机环境达到“可构建、可启动、可 smoke、可交接”的状态。

这不是生产部署文档，不覆盖高可用、弹性扩缩、零停机发布、外网暴露、TLS、容灾或多实例编排。

## 1. 部署范围与约束

- 操作系统：Ubuntu 24.04
- 前端：静态构建产物
- 后端：FastAPI + uvicorn
- 反向代理：Nginx
- 运行模式：单机、单实例、单进程

严格禁止：

- `uvicorn --reload`
- `uvicorn --workers N`
- gunicorn 多 worker
- 同机多 backend 实例并行

唯一官方后端启动命令：

```bash
cd /path/to/kg-system/backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

## 2. 部署契约

- 前端部署产物固定为 `frontend/dist/`
- 浏览器访问同域页面
- 前端请求固定走同域 `/api`
- Nginx 将 `/api` 反代到 `127.0.0.1:8000`
- 部署入口绝不使用 Vite dev server

## 3. 运行目录治理

仓库运行态统一位于根目录 `runtime/`：

- `runtime/.run/`
  - pid、space registry、import drafts、import jobs、cleanup jobs 等运行态状态
- `runtime/logs/`
  - backend/frontend/批处理日志
- `runtime/artifacts/`
  - 衍生制品保留位

仍需长期持久化的目录：

- `runtime/.run/`
- `runtime/logs/`
- `backend/state/`

说明：

- `runtime/` 可以整体清理，但会丢失 pid、registry、导入状态、cleanup 状态与运行日志。
- `frontend/dist/` 不是持久化目录，每次发布都可重新构建。

## 4. 依赖准备

在仓库根目录执行：

```bash
bash scripts/dev/bootstrap_env.sh
```

这会补齐：

- `backend/.venv`
- `backend/requirements.txt`
- `frontend/node_modules`

## 5. 前端构建

```bash
cd /path/to/kg-system/frontend
npm ci
npm run build
```

构建完成后，由 Nginx 直接托管：

```text
frontend/dist/
```

## 6. Nginx 同域反向代理

示例配置：

```nginx
server {
    listen 80;
    server_name _;

    root /path/to/kg-system/frontend/dist;
    index index.html;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

## 7. systemd 建议

```ini
[Unit]
Description=KG System Backend (single-process validation)
After=network.target

[Service]
Type=simple
WorkingDirectory=/path/to/kg-system/backend
EnvironmentFile=/path/to/kg-system/.env
ExecStart=/path/to/kg-system/backend/.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
Restart=on-failure
RestartSec=3

[Install]
WantedBy=multi-user.target
```

## 8. 官方测试与部署前检查

从仓库根目录执行：

```bash
bash scripts/test/backend_pytest.sh -q
```

这是一条官方测试入口，不隐式启动开发栈。

## 9. 部署 smoke 与放行门槛

部署完成后必须执行：

```bash
curl -fsS http://127.0.0.1:8000/api/health
curl -fsS http://127.0.0.1:8000/api/spaces/current
bash scripts/verify/smoke_api.sh
curl -fsS http://127.0.0.1/api/health
curl -fsS http://127.0.0.1/ >/dev/null
```

放行标准：

- `/api/health` 可达
- `/api/spaces/current` 可达
- `bash scripts/verify/smoke_api.sh` 输出 `[smoke] completed`
- Nginx 同域 `/api/health` 可达
- Nginx 首页可达

## 10. 推荐发布顺序

```bash
cd /path/to/kg-system
bash scripts/dev/bootstrap_env.sh
bash scripts/test/backend_pytest.sh -q
cd frontend && npm ci && npm run build
cd ../backend && ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
sudo nginx -t
sudo systemctl reload nginx
cd /path/to/kg-system && bash scripts/verify/smoke_api.sh
```

若 smoke 未通过：

- 不视为部署完成
- 优先检查 `.env`、Nebula、ES、`runtime/` 持久化、Nginx `/api` 反代
