export type GroupedFields<T> = Array<{
  key: string;
  title: string;
  items: T[];
}>;

export function groupFields<T extends { group: string }>(
  items: T[],
  groupTitles: Record<string, string>,
): GroupedFields<T> {
  const bucket = new Map<string, T[]>();
  items.forEach((item) => {
    const list = bucket.get(item.group) || [];
    list.push(item);
    bucket.set(item.group, list);
  });
  return Array.from(bucket.entries()).map(([key, values]) => ({
    key,
    title: groupTitles[key] || key,
    items: values,
  }));
}
