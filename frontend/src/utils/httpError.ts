export type ParsedApiError = {
  status: number | null;
  code: string;
  message: string;
  reason: string;
  requestId: string;
  raw: string;
};

function tryParseJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

export function parseApiError(err: unknown): ParsedApiError {
  const raw = err instanceof Error ? err.message : String(err);
  const m = raw.match(/^HTTP\s+(\d+):\s*([\s\S]*)$/);
  if (!m) {
    return {
      status: null,
      code: "",
      message: raw,
      reason: "",
      requestId: "",
      raw,
    };
  }

  const status = Number(m[1]);
  const body = String(m[2] || "").trim();
  const parsed = tryParseJson(body) as Record<string, unknown> | null;
  const detail =
    parsed && typeof parsed === "object" && parsed.detail && typeof parsed.detail === "object"
      ? (parsed.detail as Record<string, unknown>)
      : null;

  const code = String((detail?.error_code as string) || (detail?.code as string) || (parsed?.code as string) || "");
  const reason = String((detail?.reason as string) || "");
  const requestId = String((detail?.request_id as string) || "");
  const message = String(
    (detail?.message as string) ||
      (detail && typeof detail === "string" ? detail : "") ||
      (parsed?.message as string) ||
      body ||
      raw
  );

  return {
    status: Number.isFinite(status) ? status : null,
    code,
    message,
    reason,
    requestId,
    raw,
  };
}
