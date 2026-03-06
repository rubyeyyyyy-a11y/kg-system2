export async function apiPost<T>(url: string, body: unknown, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    ...init,
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as T;
}

export async function apiGet<T>(url: string, init: RequestInit = {}): Promise<T> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as T;
}
