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

export async function uploadFile<T>(url: string, file: File, fieldName = "file", init: RequestInit = {}): Promise<T> {
  const formData = new FormData();
  formData.append(fieldName, file);
  const resp = await fetch(url, {
    method: "POST",
    body: formData,
    ...init,
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as T;
}

export async function downloadBlob(url: string, init: RequestInit = {}): Promise<Blob> {
  const resp = await fetch(url, init);
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return await resp.blob();
}
