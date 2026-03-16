import { apiGet, apiPost } from "../../../api/http";
import type { CreateSpaceRequest, CreateSpaceResp, CurrentSpaceResp, SpaceSummary } from "../types/space";

export function listSpaces(): Promise<SpaceSummary[]> {
  return apiGet<SpaceSummary[]>("/api/spaces", { spaceHeaderMode: "omit" });
}

export function getResolvedCurrentSpace(): Promise<CurrentSpaceResp> {
  return apiGet<CurrentSpaceResp>("/api/spaces/current");
}

export function getDefaultResolvedSpace(): Promise<CurrentSpaceResp> {
  return apiGet<CurrentSpaceResp>("/api/spaces/current", { spaceHeaderMode: "omit" });
}

export function getSpace(spaceName: string): Promise<SpaceSummary> {
  return apiGet<SpaceSummary>(`/api/spaces/${spaceName}`, { spaceHeaderMode: "omit" });
}

export function createSpace(body: CreateSpaceRequest): Promise<CreateSpaceResp> {
  return apiPost<CreateSpaceResp>("/api/spaces", body, { spaceHeaderMode: "omit" });
}
