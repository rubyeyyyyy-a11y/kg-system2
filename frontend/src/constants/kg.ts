export const TOP_N_VISIBLE = 30;
export const EXPAND_AUTO_REVEAL_TOPK = 20;

export const MIN_CHARS = 2;
export const SUGGEST_LIMIT = 12;
export const DEBOUNCE_MS = 250;

export const SUBGRAPH_BUDGET_PRESETS = [
  { label: "S", max_nodes: 80, max_edges: 300 },
  { label: "M", max_nodes: 140, max_edges: 900 },
  { label: "L", max_nodes: 220, max_edges: 1800 },
] as const;
