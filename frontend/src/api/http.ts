import { getCurrentSpaceSnapshot, getStoredCurrentSpace } from "../features/space/store";

export type ApiRequestInit = RequestInit & {
  spaceHeaderMode?: "auto" | "omit";
  spaceName?: string | null;
  timeoutMs?: number;
};

function buildHeaders(init: ApiRequestInit, extraHeaders?: Record<string, string>): Headers {
  const headers = new Headers(init.headers || {});
  if (extraHeaders) {
    for (const [key, value] of Object.entries(extraHeaders)) headers.set(key, value);
  }
  if (init.spaceHeaderMode !== "omit") {
    // Current-space injection is centralized here so frontend requests do not
    // silently fall back to the default space because one code path forgot the header.
    const currentSpace = String(init.spaceName || getCurrentSpaceSnapshot().currentSpace || getStoredCurrentSpace() || "").trim();
    if (currentSpace) headers.set("X-KG-Space", currentSpace);
  }
  return headers;
}

export async function apiFetchJson<T>(url: string, init: ApiRequestInit = {}): Promise<T> {
  const resp = await fetchWithTimeout(url, {
    ...init,
    headers: buildHeaders(init, init.body ? { "Content-Type": "application/json" } : undefined),
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as T;
}

export async function apiPost<T>(url: string, body: unknown, init: ApiRequestInit = {}): Promise<T> {
  return apiFetchJson<T>(url, {
    ...init,
    method: "POST",
    body: JSON.stringify(body),
  });
}

export async function apiGet<T>(url: string, init: ApiRequestInit = {}): Promise<T> {
  return apiFetchJson<T>(url, init);
}

export async function uploadFile<T>(url: string, file: File, fieldName = "file", init: ApiRequestInit = {}): Promise<T> {
  const formData = new FormData();
  formData.append(fieldName, file);
  const resp = await fetchWithTimeout(url, {
    ...init,
    method: "POST",
    headers: buildHeaders(init),
    body: formData,
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return (await resp.json()) as T;
}

export async function downloadBlob(url: string, init: ApiRequestInit = {}): Promise<Blob> {
  const resp = await fetchWithTimeout(url, {
    ...init,
    headers: buildHeaders(init),
  });
  if (!resp.ok) {
    const t = await resp.text();
    throw new Error(`HTTP ${resp.status}: ${t}`);
  }
  return await resp.blob();
}

async function fetchWithTimeout(url: string, init: ApiRequestInit): Promise<Response> {
  const { timeoutMs, signal, ...rest } = init;
  if (!timeoutMs || timeoutMs <= 0) {
    return fetch(url, { ...rest, signal });
  }
  const controller = new AbortController();
  const timeoutId = window.setTimeout(() => controller.abort(), timeoutMs);
  const abortFromCaller = () => controller.abort();
  if (signal?.aborted) controller.abort();
  signal?.addEventListener("abort", abortFromCaller, { once: true });
  try {
    return await fetch(url, { ...rest, signal: controller.signal });
  } catch (error) {
    if (controller.signal.aborted && !signal?.aborted) {
      throw new Error(`Request timeout after ${timeoutMs}ms`);
    }
    throw error instanceof Error ? error : new Error(String(error));
  } finally {
    window.clearTimeout(timeoutId);
    signal?.removeEventListener("abort", abortFromCaller);
  }
}
