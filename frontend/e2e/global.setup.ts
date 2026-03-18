import { multiSpaceFixture } from "./fixture";

async function ensureJson(url: string) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`backend check failed for ${url}: HTTP ${response.status}`);
  }
  return response.json() as Promise<unknown>;
}

function delay(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms));
}

async function ensureJsonWithRetry(url: string, retries: number, delayMs: number) {
  let lastError: unknown = null;
  for (let attempt = 1; attempt <= retries; attempt += 1) {
    try {
      return await ensureJson(url);
    } catch (error) {
      lastError = error;
      if (attempt < retries) {
        await delay(delayMs);
      }
    }
  }
  throw new Error(`backend readiness check failed for ${url} after ${retries} attempts: ${String(lastError)}`);
}

export default async function globalSetup() {
  if (process.env.E2E_SKIP_BACKEND_CHECK === "1") {
    return;
  }
  const backendBase = process.env.E2E_BACKEND_URL || "http://127.0.0.1:8000";
  const retries = Number(process.env.E2E_BACKEND_CHECK_RETRIES || 20);
  const delayMs = Number(process.env.E2E_BACKEND_CHECK_DELAY_MS || 1000);
  const spacesPayload = (await ensureJsonWithRetry(`${backendBase}/api/spaces`, retries, delayMs)) as
    | Array<{
        space_name?: string;
        graph_status?: string;
        search_status?: string;
      }>
    | {
        spaces?: Array<{
          space_name?: string;
          graph_status?: string;
          search_status?: string;
        }>;
      };
  const spaces = Array.isArray(spacesPayload) ? spacesPayload : spacesPayload.spaces || [];
  const spaceMap = new Map(spaces.map((item) => [String(item.space_name || ""), item]));

  for (const space of [multiSpaceFixture.spaces.demo, multiSpaceFixture.spaces.small]) {
    const found = spaceMap.get(space.spaceName);
    if (!found) {
      throw new Error(`required E2E space is missing from /api/spaces: ${space.spaceName}`);
    }
    if (String(found.graph_status || "") !== space.readiness.graphStatus) {
      throw new Error(
        `space ${space.spaceName} graph_status mismatch: expected ${space.readiness.graphStatus}, got ${String(found.graph_status || "")}`
      );
    }
    if (String(found.search_status || "") !== space.readiness.searchStatus) {
      throw new Error(
        `space ${space.spaceName} search_status mismatch: expected ${space.readiness.searchStatus}, got ${String(found.search_status || "")}`
      );
    }
  }
}
