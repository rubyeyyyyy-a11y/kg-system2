# Import Batch Governance 测试与回归运行说明

## 1. 目标与范围

本说明用于稳定复现以下回归：

- Playwright mock e2e 主路径（含 import batch cleanup UI）
- Quick Cleanup 兼容路径
- 非 mock 的真实后端 cleanup smoke（preview + execute + search/suggest 验证）

## 2. 运行前置依赖

### 2.1 基础依赖

```bash
bash scripts/bootstrap_env.sh
```

确保后端可用（默认 `http://127.0.0.1:8000`）：

```bash
bash scripts/start_stack.sh
bash scripts/check_stack.sh
```

### 2.2 Playwright 浏览器与系统依赖（Ubuntu/WSL）

推荐标准路径：

```bash
cd frontend
npx playwright install --with-deps chromium
```

若不使用 `--with-deps`，至少保证系统安装了 Chromium 运行库（示例）：

```bash
sudo apt-get update
sudo apt-get install -y \
  libnspr4 libnss3 libasound2 libatk-bridge2.0-0 libcups2 libdrm2 libgbm1 \
  libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
  libgtk-3-0 libpango-1.0-0 libcairo2 libatspi2.0-0
```

无 sudo 应急方案（非推荐，仅临时）：

- 仅在当前 shell 注入 `LD_LIBRARY_PATH`，不要写入业务脚本
- 示例：

```bash
export LD_LIBRARY_PATH="/path/to/user-libs:${LD_LIBRARY_PATH:-}"
cd frontend && npm run e2e:import-mock
```

## 3. Playwright 运行方式（已收口）

当前 Playwright 默认行为：

- 使用 `npm run dev:e2e` 启动测试专用 Vite：`127.0.0.1:4173` + `--strictPort`
- `webServer.reuseExistingServer` 默认开启（优先减少端口冲突与手工重启）
- `e2e/global.setup.ts` 支持后端 readiness 重试，并支持通过 `E2E_SKIP_BACKEND_CHECK=1` 跳过后端检查（供 mock e2e 使用）
- `frontend/package.json` 的 e2e 脚本会显式注入 `NO_PROXY/no_proxy=127.0.0.1,localhost`，避免代理导致的 webServer 误判（典型现象：探测 HTTP 400 但浏览器实际 `ERR_CONNECTION_REFUSED`）

常用环境变量：

- `E2E_BACKEND_URL`：指定后端地址（默认 `http://127.0.0.1:8000`）
- `E2E_SKIP_BACKEND_CHECK=1`：跳过全局后端校验（仅 mock 套件建议）
- `E2E_REUSE_EXISTING_SERVER=0`：强制不复用已有前端进程

## 4. 推荐回归命令

### 4.1 mock 主路径 e2e（import + cleanup）

```bash
cd frontend
npm run e2e:import-mock
```

### 4.2 Quick Cleanup 兼容路径 e2e

```bash
cd frontend
npm run e2e:quick-cleanup
```

### 4.3 非 mock cleanup smoke（真实后端）

```bash
python3 scripts/smoke_import_cleanup.py
```

可选参数（示例）：

```bash
SMOKE_BACKEND_BASE=http://127.0.0.1:8000 \
SMOKE_CLEANUP_SPACE_NAME=it_cleanup_smoke_manual \
python3 scripts/smoke_import_cleanup.py
```

### 4.4 前端 build

```bash
cd frontend
npm run build
```

### 4.5 后端 tests（按需）

```bash
bash scripts/backend_pytest.sh backend/tests/test_imports_api.py
```

## 5. 已知限制与边界

- `frontend/e2e/specs/08-09` 属于 mock 驱动回归；不验证真实后端数据链路。
- `scripts/smoke_import_cleanup.py` 依赖真实后端 + Nebula + ES，并会创建独立测试 space。
- 真实 cleanup smoke 对索引可见性有短暂等待，若环境负载高可能需要提高 `SMOKE_CLEANUP_TIMEOUT_SEC`。
- Ubuntu/WSL 缺失系统库时，Playwright Chromium 会在启动阶段失败；优先走标准依赖安装，不建议长期使用 `LD_LIBRARY_PATH` workaround。
- 若手工执行 `playwright test`（未走 npm 脚本）且机器配置了 `HTTP_PROXY/HTTPS_PROXY`，可能再次触发 webServer 探测 400 的误判，需手动补 `NO_PROXY=127.0.0.1,localhost`。
