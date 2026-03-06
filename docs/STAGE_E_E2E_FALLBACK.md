# 阶段E：E2E 缺依赖的降级处理（2026-03-06）

## 1. 当前结论

- 当前仓库内没有正式入库的浏览器级 E2E 测试套件（未发现 `playwright.config.*`、`e2e/`、`tests/e2e/` 等配置）。
- 当前机器浏览器运行环境不完整，已有失败记录为：
  - `chrome-headless-shell: error while loading shared libraries: libnspr4.so`
- 因此，本阶段不能把结果表述为“完整 E2E 已恢复”。
- 本阶段可交付的是：
  - 缺失依赖说明
  - 可执行的替代验证路径
  - 后续恢复完整 E2E 的步骤

## 2. 当前机器缺失依赖

系统信息：

- OS: Ubuntu 24.04.3 LTS
- 包管理器：`apt-get`
- `sudo`：可用

当前机上已发现：

- 存在：`libxkbcommon.so.0`、`libgbm.so.1`、`libdrm.so.2`、`libatk-1.0.so.0`
- 缺失：`libnspr4.so`
- 未在 `ldconfig -p` 中发现：`libnss3.so`

建议优先补齐：

```bash
sudo apt-get update
sudo apt-get install -y libnspr4 libnss3
```

如果后续启用 Playwright/Chromium，建议一并补齐常见浏览器依赖：

```bash
sudo apt-get update
sudo apt-get install -y \
  libnspr4 \
  libnss3 \
  libasound2t64 \
  libatk1.0-0 \
  libcups2t64 \
  libdbus-1-3 \
  libdrm2 \
  libgbm1 \
  libglib2.0-0 \
  libgtk-3-0 \
  libx11-xcb1 \
  libxcb1 \
  libxcomposite1 \
  libxdamage1 \
  libxext6 \
  libxfixes3 \
  libxkbcommon0 \
  libxrandr2 \
  libxrender1 \
  libxshmfence1 \
  libcairo2 \
  libpango-1.0-0 \
  fonts-liberation
```

## 3. 当前可执行替代方案

### 3.1 标准化 smoke 回归

```bash
bash scripts/start_stack.sh
bash scripts/verify_stack.sh
bash scripts/smoke_api.sh
bash scripts/stop_stack.sh
```

说明：

- `verify_stack.sh`：检查前后端进程与基础可达性
- `smoke_api.sh`：执行最小 API 回归，覆盖：
  - `GET /api/health`
  - `GET /api/entity_types`
  - `GET /api/relation_types?limit=20&offset=0`
  - `POST /api/search`
  - `POST /api/subgraph`

可选环境变量：

```bash
SMOKE_SEARCH_Q=ca SMOKE_ROOT_VID=1 bash scripts/smoke_api.sh
```

### 3.2 手工验证清单

当前无法跑浏览器级自动化时，至少执行以下手工回归：

1. 打开前端首页，确认页面正常加载，无白屏。
2. 输入一个搜索词，执行搜索，确认左侧结果列表返回节点。
3. 选中一个结果，点击“加载子图”或“加载选中节点子图”，确认中间画布出现图数据。
4. 点击节点，确认右侧详情面板可加载节点详情。
5. 打开关系筛选面板，确认列表可搜索、可加载更多、可应用筛选。
6. 在图上触发一次 `加载更多边` 或 `Expand 1-hop`，确认系统能返回裁剪/预算提示而不是卡死。

## 4. 恢复完整 E2E 的步骤

当前恢复完整 E2E 需要同时满足两类条件：

### 4.1 环境层恢复

1. 安装浏览器系统依赖（见上文 `apt-get install`）。
2. 安装浏览器二进制。

如果仓库后续引入 Playwright：

```bash
npm install -D @playwright/test
npx playwright install chromium
```

如需让 Playwright 自动补系统依赖：

```bash
sudo npx playwright install-deps chromium
```

### 4.2 仓库层恢复

当前仓库并没有正式入库的 Playwright/E2E 套件，因此仅安装依赖还不够。后续还需要补：

1. `playwright.config.*`
2. `tests/e2e/` 或同等目录结构
3. 基础 smoke 用例
4. 在具备浏览器依赖的 runner 或 CI 中执行 `npx playwright test`

建议第一批浏览器级 smoke 用例只覆盖高价值主链路：

1. 首页打开
2. 搜索节点
3. 加载子图
4. 打开关系筛选
5. 点击节点查看详情

## 5. 诚实结论

- 当前机器上，完整浏览器级 E2E 仍未恢复。
- 当前阶段已补齐“可执行替代验证路径”，可以支持后续 agent 快速确认系统是否可用。
- 真正恢复完整 E2E，需要后续把浏览器依赖和仓库内测试套件一起补齐。
