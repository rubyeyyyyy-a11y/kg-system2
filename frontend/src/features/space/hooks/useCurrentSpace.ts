import { useSyncExternalStore } from "react";

import {
  completeCurrentSpaceSwitch,
  getCurrentSpaceSnapshot,
  requestCurrentSpaceSwitch,
  setStoredCurrentSpace,
  subscribeCurrentSpace,
  updateCurrentSpaceSwitch,
} from "../store";

export function useCurrentSpace() {
  const snapshot = useSyncExternalStore(
    subscribeCurrentSpace,
    getCurrentSpaceSnapshot,
    () => ({
      currentSpace: "",
      isSwitching: false,
      switchTarget: null,
      switchPhase: "idle" as const,
      switchError: null,
      switchNonce: 0,
    })
  );
  return {
    currentSpace: snapshot.currentSpace,
    setCurrentSpace: requestCurrentSpaceSwitch,
    hydrateCurrentSpace: setStoredCurrentSpace,
    completeCurrentSpaceSwitch,
    updateCurrentSpaceSwitch,
    switchState: snapshot,
  };
}
