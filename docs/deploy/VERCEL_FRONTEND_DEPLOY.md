# Vercel Frontend Deploy

本仓库前端是 `frontend/` 下的独立 `Vite` 应用，建议通过仓库根目录的 `vercel.json` 直接部署到 Vercel。

## 当前部署策略

- Vercel 只负责托管前端静态产物
- 构建命令固定为 `cd frontend && npm run build`
- 输出目录固定为 `frontend/dist`
- 浏览器仍然请求同域 `/api/*`
- Vercel 通过路由规则把 `/api/*` 代理到外部后端 `BACKEND_URL`

这意味着前端业务代码不需要改成显式后端域名，和当前仓库的相对路径 API 契约保持一致。

## 必填环境变量

在 Vercel Project Settings 里添加：

```text
BACKEND_URL=https://your-backend.example.com
```

要求：

- 不要带结尾 `/`
- 后端必须已经可从公网访问
- 后端需要正常响应 `https://your-backend.example.com/api/*`

示例：

```text
BACKEND_URL=https://kg-api.example.com
```

## CLI 部署

在仓库根目录执行：

```bash
npx vercel
```

首次创建项目时，保持默认即可；由于根目录已有 `vercel.json`，Vercel 会直接使用：

- `installCommand`
- `buildCommand`
- `outputDirectory`

生产部署：

```bash
npx vercel --prod
```

## Dashboard 检查项

部署完成后，确认：

- Framework Preset 为 `Vite` 或由 `vercel.json` 接管
- Environment Variables 中已设置 `BACKEND_URL`
- 访问首页可返回前端页面
- 访问 `/api/health` 时会被代理到你的后端

## 适用边界

当前方案只部署前端。

- 如果后端还只跑在 `127.0.0.1:8000`，Vercel 无法访问，页面 API 会失败
- 如果后端需要鉴权、白名单或额外请求头，需要在后端公网入口一并配置
