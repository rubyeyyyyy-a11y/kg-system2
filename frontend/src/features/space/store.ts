const STORAGE_KEY = "kg:current-space";

const listeners = new Set<() => void>();

export type CurrentSpaceSwitchPhase = "idle" | "persisted" | "resetting" | "refreshing_status";

export type CurrentSpaceSnapshot = {
  currentSpace: string;
  isSwitching: boolean;
  switchTarget: string | null;
  switchPhase: CurrentSpaceSwitchPhase;
  switchError: string | null;
  switchNonce: number;
};

function readStoredCurrentSpaceValue(): string {
  if (typeof window === "undefined") return "";
  return String(window.localStorage.getItem(STORAGE_KEY) || "").trim();
}

let currentSpaceSnapshot: CurrentSpaceSnapshot = {
  currentSpace: readStoredCurrentSpaceValue(),
  isSwitching: false,
  switchTarget: null,
  switchPhase: "idle",
  switchError: null,
  switchNonce: 0,
};

function emitStoreChange(): void {
  listeners.forEach((listener) => listener());
}

export function getStoredCurrentSpace(): string {
  return currentSpaceSnapshot.currentSpace || readStoredCurrentSpaceValue();
}

export function setStoredCurrentSpace(spaceName: string): void {
  const next = String(spaceName || "").trim();
  if (typeof window !== "undefined") {
    if (next) window.localStorage.setItem(STORAGE_KEY, next);
    else window.localStorage.removeItem(STORAGE_KEY);
  }
  currentSpaceSnapshot = {
    currentSpace: next,
    isSwitching: false,
    switchTarget: null,
    switchPhase: "idle",
    switchError: null,
    switchNonce: currentSpaceSnapshot.switchNonce,
  };
  emitStoreChange();
}

export function getCurrentSpaceSnapshot(): CurrentSpaceSnapshot {
  return currentSpaceSnapshot;
}

export function requestCurrentSpaceSwitch(spaceName: string): CurrentSpaceSnapshot {
  const next = String(spaceName || "").trim();
  if (!next) return currentSpaceSnapshot;
  if (
    currentSpaceSnapshot.currentSpace === next &&
    (!currentSpaceSnapshot.isSwitching || currentSpaceSnapshot.switchTarget === next)
  ) {
    return currentSpaceSnapshot;
  }
  if (typeof window !== "undefined") window.localStorage.setItem(STORAGE_KEY, next);
  currentSpaceSnapshot = {
    currentSpace: next,
    isSwitching: true,
    switchTarget: next,
    switchPhase: "persisted",
    switchError: null,
    switchNonce: currentSpaceSnapshot.switchNonce + 1,
  };
  emitStoreChange();
  return currentSpaceSnapshot;
}

export function updateCurrentSpaceSwitch(
  switchNonce: number,
  patch: Partial<Pick<CurrentSpaceSnapshot, "switchPhase" | "switchError">>
): CurrentSpaceSnapshot {
  if (currentSpaceSnapshot.switchNonce !== switchNonce) return currentSpaceSnapshot;
  currentSpaceSnapshot = {
    ...currentSpaceSnapshot,
    ...patch,
  };
  emitStoreChange();
  return currentSpaceSnapshot;
}

export function completeCurrentSpaceSwitch(switchNonce: number): CurrentSpaceSnapshot {
  if (currentSpaceSnapshot.switchNonce !== switchNonce) return currentSpaceSnapshot;
  currentSpaceSnapshot = {
    ...currentSpaceSnapshot,
    isSwitching: false,
    switchTarget: null,
    switchPhase: "idle",
    switchError: null,
  };
  emitStoreChange();
  return currentSpaceSnapshot;
}

export function subscribeCurrentSpace(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export { STORAGE_KEY as CURRENT_SPACE_STORAGE_KEY };
