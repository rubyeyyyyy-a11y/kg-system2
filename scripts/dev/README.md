# `scripts/dev`

本目录只承载本地开发入口，不作为部署命令。

- `bootstrap_env.sh`：补齐 `backend/.venv` 与 `frontend/node_modules`
- `start_stack.sh`：启动本地 backend + frontend dev server
- `stop_stack.sh`：停止本地开发栈
- `common.sh`：开发/验证脚本共享的运行目录与进程检查函数

开发态约束：

- 前端入口是 Vite dev server
- 后端可使用 `uvicorn --reload`
- `runtime/.run` 与 `runtime/logs` 只服务于本地开发和验证过程
