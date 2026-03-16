import type { ComponentProps } from "react";

import { LeftSearchPanel } from "../../components/LeftSearchPanel";
import { TopBar } from "../../components/TopBar";
import { RelationFilterPanel } from "../../components/RelationFilter/RelationFilterPanel";

export type LegacyWorkspaceSidebarProps = ComponentProps<typeof LeftSearchPanel>;
export type LegacyWorkspaceTopBarProps = ComponentProps<typeof TopBar>;
export type LegacyWorkspaceRelationFilterProps = ComponentProps<typeof RelationFilterPanel>;

export function LegacyWorkspaceSidebar(props: LegacyWorkspaceSidebarProps) {
  return <LeftSearchPanel {...props} />;
}

export function LegacyWorkspaceTopBar(props: LegacyWorkspaceTopBarProps) {
  return <TopBar {...props} />;
}

export function LegacyWorkspaceRelationFilter(props: LegacyWorkspaceRelationFilterProps) {
  return <RelationFilterPanel {...props} />;
}
