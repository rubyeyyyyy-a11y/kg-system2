# 本机 Demo Step1: Backend 跑通 Runbook

本文档覆盖当前阶段唯一目标：仓库位于 Windows 文件系统，backend 在 WSL2 Ubuntu 运行，NebulaGraph 与 ES/OpenSearch 由 Windows 宿主机 Docker Desktop 提供，只要求 backend 在 WSL2 中跑起来并完成本机 smoke。

## 当前仓库确认

- backend 入口：`backend/app/main.py`
- 推荐启动命令：`cd backend && ./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info`
- backend 关键 Nebula 配置项：`NEBULA_HOST`、`NEBULA_PORT`、`NEBULA_USER`、`NEBULA_PASSWORD`、`NEBULA_SPACE`
- backend 关键 ES 配置项：`ES_ENABLED`、`ES_URL`、`ES_INDEX`
- 当前 `.env` 已生成在仓库根目录，默认指向：
  - `NEBULA_HOST=127.0.0.1`
  - `NEBULA_PORT=9669`
  - `NEBULA_SPACE=demo_kg`
  - `ES_ENABLED=1`
  - `ES_URL=http://127.0.0.1:9200`

说明：

- 当前实测 WSL2 可以直接访问 `127.0.0.1:9669` 和 `127.0.0.1:9200`，所以这一步不需要改成 Windows Host IP。
- 若你的机器后续出现 WSL2 无法访问宿主机 `127.0.0.1`，优先取 `ip route show default` 的网关 IP，或 `/etc/resolv.conf` 的 `nameserver` 作为 Windows Host IP，再把 `.env` 改成：
  - `NEBULA_HOST=<windows_host_ip>`
  - `ES_URL=http://<windows_host_ip>:9200`

## 已执行结果

- `backend/.venv` 已存在并可用
- `pip install -r backend/requirements.txt` 已完成
- `cd backend && ./.venv/bin/python -c "import app.main"` 已通过
- Nebula 真实模块校验已通过：`SHOW HOSTS;` 成功
- ES `curl` 校验已通过：`http://127.0.0.1:9200` 返回集群信息

## 启动 backend

前台启动：

```bash
cd /home/ray/kg-system/backend
./.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --log-level info
```

也可以直接用仓库脚本：

```bash
bash /home/ray/kg-system/scripts/dev/run_backend_wsl.sh foreground
```

后台启动：

```bash
bash /home/ray/kg-system/scripts/dev/run_backend_wsl.sh background
```

后台日志：

```bash
tail -f /home/ray/kg-system/runtime/logs/backend.wsl.log
```

如果 Windows 宿主机无法访问 WSL 的 `127.0.0.1:8000`，改用：

```bash
BACKEND_HOST=0.0.0.0 bash /home/ray/kg-system/scripts/dev/run_backend_wsl.sh foreground
```

## 执行本机 smoke

先确认 backend 已经启动，然后执行：

```bash
bash /home/ray/kg-system/scripts/verify/check_local_backend.sh
```

该脚本会依次输出：

- `import app.main` 是否成功
- Nebula 真实模块连通性
- ES `curl` 连通性
- `/api/health`
- `/api/spaces/current`
- `/api/import/schema`
- `/api/search`

失败归因规则：

- `dependency install problem`：Python 依赖、虚拟环境、`import app.main` 失败
- `WSL->Windows network problem`：WSL 访问宿主机 Docker 暴露端口失败
- `backend config problem`：backend 已启动但配置不对、接口 5xx、接口返回结构异常
