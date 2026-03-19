# Frontend Architecture

## Feature layout

前端以 `frontend/src/features/*` 为主组织单元。推荐目录职责如下：

- `api/`：请求封装层，只负责调用 `/api/*` 契约，不放 React 状态。
- `hooks/`：状态与交互逻辑层，负责组合 api、管理 loading/error、同步视图状态。
- `components/`：纯 UI 层，尽量通过 props 接收数据和回调，不直接发请求。
- `container/`：页面组合层，负责把多个 hooks/components 装配成一个完整工作区或页面。

当前仓库已经落地的示例：

- `features/import/api/*`：import 相关请求封装。
- `features/import/hooks/*`：import workspace 的状态流与动作流。
- `features/import/components/*`：import 的纯展示与局部交互组件。
- `features/import/container/ImportWorkspace.tsx`：import 页面容器。
- `features/discovery/container/DiscoveryWorkspace.tsx`：discovery 页面组合入口。

## Layer rules

- `api` 不依赖 React 组件。
- `hooks` 不直接 `fetch`，统一走 `api/` 或 `src/api/*`。
- `components` 不直接访问网络，不持有跨页面业务流程状态。
- `container` 负责页面装配，可以组合多个 feature hooks/components。

## Current boundary status

- 当前 `features/import/hooks/*` 已统一通过 `features/import/api/import.ts` 调后端。
- 当前 `features/space/hooks/*` 已统一通过 `features/space/api/space.ts` 调后端。
- 当前 `src/api/http.ts` 是底层 HTTP 适配层；新代码优先在 feature `api/` 中包一层领域接口。
- 当前 discovery 仍有一批共享 hooks 留在 `frontend/src/hooks/`。这是历史收口中的保留区，新逻辑不要继续把 feature 业务堆回根级 `src/hooks/`。

## Known TODO

- `frontend/src/components/DiscoveryPanel.tsx` 目前仍是一个较大的纯 UI 组件，虽然没有直接请求，但承载了较多交互展示分支。后续若继续演进 discovery，优先在 feature 内拆出更细的 `components/` 子组件，而不是继续增厚根级组件。
- `frontend/src/app/AppShell.tsx` 仍在组合若干根级共享 hooks；这是当前工作区总装层，后续新增页面级编排应优先落在 feature `container/` 下。
