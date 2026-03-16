import { useEffect, useRef } from "react";

import { parseApiError } from "../../../utils/httpError";
import { useCurrentSpace } from "./useCurrentSpace";

type UseSpaceSwitchCoordinatorParams = {
  currentSpace: string;
  refreshSpaceState: () => Promise<void>;
  resetSpaceScopedState: (nextSpace: string) => void;
  onSwitchNotice?: (notice: { level: "error" | "warn" | "info"; message: string } | null) => void;
};

export function useSpaceSwitchCoordinator({
  currentSpace,
  refreshSpaceState,
  resetSpaceScopedState,
  onSwitchNotice,
}: UseSpaceSwitchCoordinatorParams) {
  const { switchState, updateCurrentSpaceSwitch, completeCurrentSpaceSwitch } = useCurrentSpace();
  const activeNonceRef = useRef(0);

  useEffect(() => {
    if (!switchState.isSwitching) return;
    if (!currentSpace) return;
    if (switchState.switchTarget !== currentSpace) return;
    if (activeNonceRef.current === switchState.switchNonce) return;

    activeNonceRef.current = switchState.switchNonce;
    let cancelled = false;

    const run = async () => {
      updateCurrentSpaceSwitch(switchState.switchNonce, { switchPhase: "resetting", switchError: null });
      resetSpaceScopedState(currentSpace);
      updateCurrentSpaceSwitch(switchState.switchNonce, { switchPhase: "refreshing_status" });

      try {
        await refreshSpaceState();
        if (cancelled) return;
        completeCurrentSpaceSwitch(switchState.switchNonce);
      } catch (error) {
        if (cancelled) return;
        const parsed = parseApiError(error);
        updateCurrentSpaceSwitch(switchState.switchNonce, {
          switchPhase: "refreshing_status",
          switchError: parsed.message || "space refresh failed",
        });
        completeCurrentSpaceSwitch(switchState.switchNonce);
        onSwitchNotice?.({ level: "error", message: `space 切换后的状态刷新失败：${parsed.message}` });
      }
    };

    void run();

    return () => {
      cancelled = true;
    };
  }, [
    completeCurrentSpaceSwitch,
    currentSpace,
    onSwitchNotice,
    refreshSpaceState,
    resetSpaceScopedState,
    switchState.isSwitching,
    switchState.switchNonce,
    switchState.switchTarget,
    updateCurrentSpaceSwitch,
  ]);

  return switchState;
}
