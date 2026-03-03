import { memo, useMemo, useState } from "react";
import type { CSSProperties, ReactElement } from "react";

export type ListChildComponentProps<TData> = {
  index: number;
  style: CSSProperties;
  data: TData;
};

type FixedSizeListProps<TData> = {
  height: number;
  width: number | string;
  itemCount: number;
  itemSize: number;
  itemData: TData;
  overscanCount?: number;
  children: (props: ListChildComponentProps<TData>) => ReactElement | null;
};

function FixedSizeListInner<TData>({
  height,
  width,
  itemCount,
  itemSize,
  itemData,
  overscanCount = 4,
  children,
}: FixedSizeListProps<TData>) {
  const [scrollTop, setScrollTop] = useState(0);

  const { startIndex, endIndex, totalHeight } = useMemo(() => {
    const safeCount = Math.max(0, itemCount);
    const safeSize = Math.max(1, itemSize);
    const visibleCount = Math.max(1, Math.ceil(height / safeSize));
    const start = Math.max(0, Math.floor(scrollTop / safeSize) - overscanCount);
    const end = Math.min(safeCount - 1, start + visibleCount + overscanCount * 2);
    return {
      startIndex: start,
      endIndex: end,
      totalHeight: safeCount * safeSize,
    };
  }, [height, itemCount, itemSize, overscanCount, scrollTop]);

  const rows: ReactElement[] = [];
  for (let i = startIndex; i <= endIndex; i += 1) {
    rows.push(
      <div
        key={i}
        style={{
          position: "absolute",
          top: i * itemSize,
          left: 0,
          width: "100%",
          height: itemSize,
        }}
      >
        {children({
          index: i,
          data: itemData,
          style: {
            width: "100%",
            height: itemSize,
          },
        })}
      </div>
    );
  }

  return (
    <div
      style={{
        width,
        height,
        overflowY: "auto",
        overflowX: "hidden",
      }}
      onScroll={(e) => {
        setScrollTop((e.currentTarget as HTMLDivElement).scrollTop);
      }}
    >
      <div style={{ position: "relative", width: "100%", height: totalHeight }}>{rows}</div>
    </div>
  );
}

export const FixedSizeList = memo(FixedSizeListInner) as typeof FixedSizeListInner;
