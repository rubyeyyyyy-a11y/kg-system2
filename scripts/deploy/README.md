# `scripts/deploy`

本目录保留部署相关入口说明。

当前仓库的正式部署契约已经固化为：

- 前端部署产物固定为 `frontend/dist`
- 后端部署命令固定为单进程 `uvicorn app.main:app`
- 部署态禁止 `--reload`
- 部署态禁止多 worker / 多实例

具体操作标准以 `docs/INTRANET_SINGLE_HOST_DEPLOY_RUNBOOK.md` 为准。
