import { useState } from "react";

import { parseApiError } from "../../../utils/httpError";
import { createSpace } from "../api/space";
import { requestCurrentSpaceSwitch } from "../store";
import type { CreateSpaceRequest, CreateSpaceResp } from "../types/space";

export function useCreateSpace() {
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(body: CreateSpaceRequest, options: { autoSelect?: boolean } = {}): Promise<CreateSpaceResp> {
    setSubmitting(true);
    setError(null);
    try {
      const resp = await createSpace(body);
      if (options.autoSelect !== false) requestCurrentSpaceSwitch(resp.space.space_name);
      return resp;
    } catch (err) {
      const parsed = parseApiError(err);
      setError(parsed.message || "create space failed");
      throw err;
    } finally {
      setSubmitting(false);
    }
  }

  return {
    createSpace: submit,
    submitting,
    error,
  };
}
