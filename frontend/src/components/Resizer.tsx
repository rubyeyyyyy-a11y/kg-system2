import type { PointerEvent } from "react";

type ResizerProps = {
  side: "left" | "right";
  onPointerDown: (e: PointerEvent<HTMLDivElement>) => void;
};

export function Resizer({ side, onPointerDown }: ResizerProps) {
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label={side === "left" ? "Resize left panel" : "Resize right panel"}
      className={`kg-resizer kg-resizer-${side}`}
      onPointerDown={onPointerDown}
    />
  );
}
