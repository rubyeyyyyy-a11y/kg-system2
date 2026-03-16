import { useCallback, useEffect, useMemo, useRef } from "react";
import type { MutableRefObject } from "react";

import { useCurrentSpace } from "./useCurrentSpace";
import { useSpaces } from "./useSpaces";
import { useSpaceSwitchCoordinator } from "./useSpaceSwitchCoordinator";

export function useSpaceSessionController({
  legacyResetRef,
  discoveryResetRef,
  pageResetRef,
  onSwitchNotice,
}: {
  legacyResetRef: MutableRefObject<(nextSpace: string) => void>;
  discoveryResetRef: MutableRefObject<(nextSpace: string) => void>;
  pageResetRef: MutableRefObject<(nextSpace: string) => void>;
  onSwitchNotice?: (notice: { level: "error" | "warn" | "info"; message: string } | null) => void;
}) {
  const { currentSpace, setCurrentSpace, switchState: currentSpaceStore } = useCurrentSpace();
  const { spaces, resolvedCurrent, loading: spacesLoading, error: spacesError, refresh: refreshSpaces } = useSpaces();
  const effectiveCurrentSpace = currentSpace || resolvedCurrent?.space_name || "";
  const activeSpaceRef = useRef(effectiveCurrentSpace);

  useEffect(() => {
    activeSpaceRef.current = effectiveCurrentSpace;
  }, [effectiveCurrentSpace]);

  const selectedSpaceSummary = useMemo(
    () => spaces.find((item) => item.space_name === effectiveCurrentSpace) || null,
    [effectiveCurrentSpace, spaces]
  );

  const resetSpaceScopedState = useCallback(
    (nextSpace: string) => {
      legacyResetRef.current(nextSpace);
      discoveryResetRef.current(nextSpace);
      pageResetRef.current(nextSpace);
      onSwitchNotice?.({ level: "info", message: `已切换到 ${nextSpace}，搜索与统一关系发现范围已同步到该 space。` });
    },
    [discoveryResetRef, legacyResetRef, onSwitchNotice, pageResetRef]
  );

  const spaceSwitchState = useSpaceSwitchCoordinator({
    currentSpace: effectiveCurrentSpace,
    refreshSpaceState: refreshSpaces,
    resetSpaceScopedState,
    onSwitchNotice,
  });

  const currentSpaceStatus = selectedSpaceSummary?.status || resolvedCurrent?.registry_status || "";
  const currentSpaceGraphStatus = selectedSpaceSummary?.graph_status || resolvedCurrent?.graph_status || "unavailable";
  const currentSpaceSearchStatus = selectedSpaceSummary?.search_status || resolvedCurrent?.search_status || "unavailable";
  const currentSpaceCoveragePct =
    selectedSpaceSummary?.coverage_pct ?? resolvedCurrent?.coverage_pct ?? selectedSpaceSummary?.index_status?.coverage_pct ?? null;
  const currentSpaceIndexStatus = selectedSpaceSummary?.index_status || resolvedCurrent?.index_status || null;
  const spaceSwitchBlocked = spaceSwitchState.isSwitching;
  const spaceSwitchPhaseLabel =
    spaceSwitchState.switchPhase === "resetting"
      ? "resetting previous space state"
      : spaceSwitchState.switchPhase === "refreshing_status"
        ? "refreshing readiness and index status"
        : "persisting current space";

  const guardSpaceScopedRequest = useCallback(
    (actionLabel: string) => {
      if (spaceSwitchBlocked) {
        onSwitchNotice?.({
          level: "info",
          message: `正在切换 current space 到 ${effectiveCurrentSpace || spaceSwitchState.switchTarget || "-"}，${actionLabel}会在 readiness / index status 刷新完成后恢复。`,
        });
        return false;
      }
      if (!effectiveCurrentSpace) {
        onSwitchNotice?.({ level: "warn", message: `${actionLabel}已阻止：当前 space 尚未解析。` });
        return false;
      }
      return true;
    },
    [effectiveCurrentSpace, onSwitchNotice, spaceSwitchBlocked, spaceSwitchState.switchTarget]
  );

  return {
    currentSpace,
    setCurrentSpace,
    currentSpaceStore,
    spaces,
    resolvedCurrent,
    spacesLoading,
    spacesError,
    refreshSpaces,
    effectiveCurrentSpace,
    activeSpaceRef,
    selectedSpaceSummary,
    currentSpaceStatus,
    currentSpaceGraphStatus,
    currentSpaceSearchStatus,
    currentSpaceCoveragePct,
    currentSpaceIndexStatus,
    spaceSwitchState,
    spaceSwitchBlocked,
    spaceSwitchPhaseLabel,
    guardSpaceScopedRequest,
  };
}
