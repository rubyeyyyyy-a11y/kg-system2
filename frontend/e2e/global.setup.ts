import { multiSpaceFixture } from "./fixture";

async function ensureJson(url: string) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`backend check failed for ${url}: HTTP ${response.status}`);
  }
  return response.json() as Promise<unknown>;
}

export default async function globalSetup() {
  const backendBase = process.env.E2E_BACKEND_URL || "http://127.0.0.1:8000";
  const spacesPayload = (await ensureJson(`${backendBase}/api/spaces`)) as
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
