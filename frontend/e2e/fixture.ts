import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

type SpaceFixture = {
  spaceName: string;
  searchTerm: string;
  suggestTerm: string;
  rawIdTerm: string;
  expected: {
    label: string;
    vid: number;
    rawId: string;
  };
  readiness: {
    registryStatus: string;
    graphStatus: string;
    searchStatus: string;
    indexStatus: string;
  };
};

type MultiSpaceFixture = {
  generated_at: string;
  source_priority: string[];
  spaces: {
    demo: SpaceFixture;
    small: SpaceFixture;
  };
};

const dirname = path.dirname(fileURLToPath(import.meta.url));
const fixturePath = path.resolve(dirname, "fixtures", "multi-space.json");

export const multiSpaceFixture = JSON.parse(fs.readFileSync(fixturePath, "utf8")) as MultiSpaceFixture;

export type { MultiSpaceFixture, SpaceFixture };
