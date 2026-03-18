# Property System Upgrade Plan

## Goal

在保持单 `Entity` / 单 `REL2` 物理模型不变的前提下，把当前系统升级成一套真正可治理的属性体系：

- 属性成为一等公民，而不是 `props` JSON 折叠兜底
- 详情、编辑、导入共用同一套字段治理规则
- 节点按统一字段基表 + 实际非空属性动态渲染
- 边按公共字段 + 语义类型驱动的专属字段动态渲染
- 导入改成固定字段显式映射 + 未知列保真保留
- dropped/hidden panel 默认态收口到统一 UI 配置

## 基于现有代码的关键判断

当前仓库里，问题已经不是“能力缺失”，而是“能力被旧规则卡住”：

- 详情链路已经能拿到全量属性。`backend/app/services/detail_service.py` 已经返回 `properties(v)` / `properties(e)`。
- 详情前端仍是固定模板。`frontend/src/components/RightDetailPanel.tsx` 只展示少量顶层字段，`props` 仍以折叠 JSON 呈现。
- 编辑链路被静态白名单锁死。`frontend/src/components/EditWritebackPanel.tsx` 完全依赖 `/api/schema/editable_fields`，而 `backend/app/core/field_policy.py` + `backend/app/core/config.py` 只允许固定字段。
- 导入执行层其实已经支持任意属性。`backend/app/services/imports/import_ngql_service.py` 和 `mapping_service.py` 可以写任意 `property_mappings`。
- 导入默认策略仍然过于保守。`backend/app/services/team_ingestion/adapters/standard_csv_to_draft.py`、`backend/app/services/imports/source_service.py`、`frontend/src/features/import/ImportWorkspace.tsx` 都还在做固定字段别名压缩。

结论：这次最值得做的，不是继续补模板，而是补一个统一的“属性治理层”。

## 对原方案的两个关键优化

### 1. 不建议把新的语义字段继续命名成 `edge_type`

这是当前代码结构里最容易埋长期雷的地方。

仓库里 `edge_type` 已经稳定表示“物理边标签 / API identity”，例如：

- `frontend/src/types/kg.ts`
- `frontend/src/components/EditWritebackPanel.tsx`
- `backend/app/schemas/detail.py`
- `backend/app/services/detail_service.py`
- `backend/app/services/edit_service.py`

如果再往 `REL2.props` 里塞一个同名语义字段 `edge_type`，详情、编辑、导入、选择态、patch identity 会长期混淆。

工程上更好的做法：

- 物理层继续保留 `edge_type=REL2`
- 新增一个语义主键字段，推荐命名为 `edge_kind`

`edge_kind` 在职责上完全等价于你原方案里的“边类型 registry 主键”：

- 边详情字段分组主键
- 边编辑表单生成主键
- 导入类型专属字段挂载主键
- 后续 metadata 覆盖层主键

如果你业务上必须坚持使用字面量 `edge_type`，那就应该反过来做一次更大的协议重命名，把当前 API identity 的 `edge_type` 全面改成 `storage_edge_type`。但基于当前代码规模，我更推荐直接引入 `edge_kind`。

### 2. 不要把 metadata 服务化放到最后，应该先落一个“治理内核”

你原来的 Phase 4 是“metadata 服务化”，这个方向对，但顺序可以更激进。

更适合当前仓库的做法是：

- 先补一层前后端都能复用的字段规则中心
- 详情和编辑先切到这层
- 导入默认映射再切到这层
- 最后再把这层通过 API 暴露成服务

也就是说，先做“治理内核”，后做“远程服务化”。

## 推荐的最终架构

### Backend

新增一个属性治理域，不再把规则散落在 `config.py`、`field_policy.py`、前端组件常量里。

建议目录：

```text
backend/app/object_meta/
  models.py
  node_rules.py
  edge_rules.py
  layout_service.py
  validation_service.py
  import_rules.py
```

职责建议：

- `models.py`
  - `FieldRule`
  - `FieldGroup`
  - `ObjectLayout`
  - `LongTextRule`
- `node_rules.py`
  - 节点基表字段
  - 节点字段分组
  - 节点只读字段
- `edge_rules.py`
  - 边公共字段
  - `edge_kind` 覆盖规则
  - 边只读字段
- `layout_service.py`
  - 根据 detail snapshot + props 生成结构化 layout
- `validation_service.py`
  - 替代当前 `field_policy.py`
  - 统一判断字段是否可编辑、类型如何校验、空值如何处理
- `import_rules.py`
  - 固定字段映射规则
  - 未知列保留规则
  - 别名映射策略

### Frontend

把现有右侧单文件拆成 feature 域，而不是继续堆在 `RightDetailPanel.tsx`。

建议目录：

```text
frontend/src/features/detail/
  components/
    NodeDetailView.tsx
    EdgeDetailView.tsx
    DetailSection.tsx
    DetailField.tsx
    ExpandableText.tsx
    RawJsonDebugSection.tsx
  hooks/
    useNormalizedDetail.ts
    useDetailLayout.ts
  utils/
    normalizeDetail.ts
    groupFields.ts
    formatValue.ts

frontend/src/features/edit/
  components/
    DynamicEditForm.tsx
    EditSection.tsx
    EditField.tsx
  hooks/
    useEditLayout.ts
    useEditDraft.ts

frontend/src/features/objectMeta/
  registry/
    commonRules.ts
    nodeRules.ts
    edgeRules.ts
  config/
    panelDefaults.ts
```

`frontend/src/components/RightDetailPanel.tsx` 只保留 shell：

- tab 切换
- 布局
- 调用 detail/edit feature
- 发现态相关按钮外壳

## API 与协议建议

### 1. Detail API

短期不必推翻现有 detail API；先保持返回 `props`，前端通过 normalize 过渡。

但建议尽快把 detail payload 统一成更稳定的结构：

```json
{
  "object_type": "node|edge",
  "identity": {},
  "summary": {},
  "system": {},
  "props": {},
  "layout_key": "Entity|REL2:edge_kind"
}
```

这样 detail/edit/import 可以围绕同一个 `layout_key` 说话。

### 2. Editable schema API

不再继续强化 `/api/schema/editable_fields` 的固定返回结构。

建议新增：

- `GET /api/object-meta/detail-layout`
- `GET /api/object-meta/edit-layout`

或者一个合并接口：

- `POST /api/object-meta/layout`

输入：

- object kind
- node detail / edge detail identity

输出：

- 字段分组
- 字段顺序
- 字段标签
- 只读性
- 长文本策略
- 可编辑性
- 未注册字段落点

原 `/api/schema/editable_fields` 可以先保留为兼容层，最终下线。

### 3. Patch 协议

`PATCH /api/node` 和 `PATCH /api/edge` 不需要重做。

保留：

- `set: Record<string, unknown>`
- `expected_version`
- `updated_by`

要改的是内部校验路径：

- 当前：`field_policy.py` 固定白名单
- 目标：`object_meta.validation_service` 动态规则校验

## 详情层的最终落地方式

### 节点

节点不建议上重量级 per-type schema。

节点详情按下面顺序生成：

1. 标题区
   - `entity_name`
   - `entity_type`
2. 基础信息
   - `vid`
   - `entity_type`
   - `entity_raw_id`
   - `source`
   - `hop_level`
3. 业务属性
   - 从 `props` 动态生成
   - 顶层已展示字段去重
   - 仅展示非空字段
   - 按 registry 分组排序
   - 未注册字段归入“其他属性”
4. 长文本
   - `description`
   - `synonyms`
   - 其他超阈值字段
5. 系统信息
   - `version`
   - `updated_at`
   - `updated_by`
6. Raw JSON
   - 默认折叠

### 边

边详情要比节点更正式，因为字段差异更大。

边详情按下面顺序生成：

1. 标题区
   - `edge_kind`
   - `relation`
2. 连接信息
   - `src`
   - `dst`
   - `rank`
   - 物理 `edge_type`
   - `relation`
   - `source`
3. 类型专属属性
   - 基于 `edge_kind` registry
   - 未注册字段归入“其他属性”
4. 长文本
   - `evidence`
   - 其他长说明字段
5. 系统信息
   - `version`
   - `updated_at`
   - `updated_by`
6. Raw JSON
   - 默认折叠

## 编辑层的最终落地方式

### 后端

`backend/app/services/edit_service.py` 需要做三件事：

1. `_node_snapshot()` / `_edge_snapshot()` 改成动态快照
   - 不再只取固定字段
   - 需要把对象当前实际属性全部纳入比较与审计上下文

2. `field_policy` 退场
   - 当前 `backend/app/core/field_policy.py` 可保留成兼容 facade
   - 实际逻辑转发到新 `object_meta.validation_service`

3. relation / entity_type 的高风险编辑单独标规则
   - `relation` 第一阶段建议只读
   - `entity_type` 可编辑，但应有显式风险提示

### 前端

`frontend/src/components/EditWritebackPanel.tsx` 当前的主要问题不是 UI，而是“字段来源错误”。

需要重构成：

- 表单字段不再只来自 `/api/schema/editable_fields`
- 字段来源改成：
  - 基础规则
  - 当前对象已有属性
  - metadata 标记可编辑字段
- 未注册字段放入“高级属性”
- 系统字段单独只读展示

## 导入链的最终落地方式

### 1. 导入执行层尽量少改

当前 `backend/app/services/imports/import_ngql_service.py` 已经能写任意映射字段，这层不是主战场。

真正要改的是默认策略层：

- `backend/app/services/team_ingestion/adapters/standard_csv_to_draft.py`
- `backend/app/services/imports/source_service.py`
- `frontend/src/features/import/ImportWorkspace.tsx`

### 2. 节点导入规则

节点使用：

- 固定字段显式映射
- 未知列原样保留

固定字段至少包括：

- `ID`
- `entity_type`
- `entity_name`
- `entity_raw_id`
- `description`
- `source`
- `synonyms`

未知列只要不与 identity / system 冲突，全部保留为属性。

### 3. 边导入规则

边使用：

- 公共字段显式映射
- 未知列原样保留
- 写入 `edge_kind`

公共字段至少包括：

- `srcVID`
- `dstVID`
- `rank`
- `relation`
- `source`
- `evidence`
- `version`
- `updated_at`
- `updated_by`

类型专属字段不再压缩到 `evidence`。

### 4. Alias 策略要收缩

当前这些逻辑都还在做“把多列压到 evidence”的合并：

- `frontend/src/features/import/ImportWorkspace.tsx`
- `backend/app/services/imports/source_service.py`

例如：

- `pmid -> evidence`
- `relation_detail -> evidence`

这在保真目标下已经不合适。

建议改成：

- `evidence` 仍然是显式目标字段
- `pmid`、`relation_detail` 默认保留原列
- 用户可以手工映射到 `evidence`
- 系统不再默认一锅炖

## dropped / hidden panel 默认态

这个改动小，但值得顺手工程化。

建议新增：

```text
frontend/src/features/objectMeta/config/panelDefaults.ts
```

例如：

```ts
export const panelDefaults = {
  discoveryDroppedPanelCollapsed: true,
  hiddenNodesCollapsed: true,
};
```

然后把这些默认值从散落的 hook 中收口：

- `frontend/src/features/discovery/hooks/useDiscoverySessionController.ts`
- 其他 hidden/dropped 面板使用方

## 推荐实施顺序

### Delivery 1: 治理内核 + Detail/Edit 一起切

不要只做详情层。

这一步建议一次完成：

- 引入 `object_meta` 规则中心
- 右侧详情拆 feature
- 编辑表单切动态生成
- Raw JSON 退到调试区
- dropped/hidden 默认折叠

收益最大，而且不会产生“看得见但改不了”的半成品。

### Delivery 2: Import Preservation + edge_kind 回填

这一步完成：

- 通用 ImportWorkspace 默认映射改造
- team-ingestion 草稿构建改造
- alias 压缩收缩
- `edge_kind` 持久化写入
- 小样本验证后重导 / 回填 demo_kg

### Delivery 3: 服务化与清理

这一步再做：

- object meta API 服务化
- 下线旧 `/api/schema/editable_fields`
- 精简 `field_policy.py` / `config.py` 中的旧白名单
- 补完整测试与文档

## 最终建议

保留单 `Entity` / 单 `REL2` 是对的，但这次不应再把重点放在“右侧面板美化”或“多加几个字段”。

更适合当前代码库的主线是：

1. 先引入统一属性治理层
2. 立刻让 detail 和 edit 同时切过去
3. 再把 import 默认策略切成保真模式
4. 最后做 metadata API 服务化和旧规则清理

如果只允许我在你原方案上做一个最重要的工程化修正，那就是：

- 不要让新的语义边类型继续叫 `edge_type`
- 用 `edge_kind` 做 registry 主键

这样你后面的 detail / edit / import / metadata 四条线才能长期干净地收口。
