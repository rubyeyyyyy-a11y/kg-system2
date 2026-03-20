const HOP_BY_HOP_HEADERS = new Set([
  "connection",
  "content-length",
  "host",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailers",
  "transfer-encoding",
  "upgrade",
])

function json(res, statusCode, payload) {
  res.statusCode = statusCode
  res.setHeader("content-type", "application/json; charset=utf-8")
  res.end(JSON.stringify(payload))
}

function normalizeBaseUrl(raw) {
  return String(raw || "").trim().replace(/\/+$/, "")
}

function buildTargetUrl(req, backendBaseUrl) {
  const incoming = new URL(req.url, "http://localhost")
  const targetPath = incoming.pathname.replace(/^\/api\/?/, "")
  const target = new URL(`${backendBaseUrl}/api/${targetPath}`)
  target.search = incoming.search
  return target
}

function forwardHeaders(req) {
  const headers = {}
  for (const [key, value] of Object.entries(req.headers || {})) {
    if (value == null) continue
    if (HOP_BY_HOP_HEADERS.has(String(key).toLowerCase())) continue
    headers[key] = Array.isArray(value) ? value.join(", ") : value
  }
  if (req.headers.host) headers["x-forwarded-host"] = req.headers.host
  headers["x-forwarded-proto"] = "https"
  return headers
}

async function readRequestBody(req) {
  if (req.method === "GET" || req.method === "HEAD") return undefined
  const chunks = []
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk))
  }
  if (!chunks.length) return undefined
  return Buffer.concat(chunks)
}

module.exports = async (req, res) => {
  const backendBaseUrl = normalizeBaseUrl(process.env.BACKEND_URL)
  if (!backendBaseUrl) {
    return json(res, 500, {
      error_code: "BACKEND_URL_MISSING",
      message: "Set BACKEND_URL to the tunnel base URL, for example https://example.trycloudflare.com",
    })
  }

  let upstream
  try {
    upstream = await fetch(buildTargetUrl(req, backendBaseUrl), {
      method: req.method,
      headers: forwardHeaders(req),
      body: await readRequestBody(req),
      redirect: "manual",
    })
  } catch (error) {
    return json(res, 502, {
      error_code: "BACKEND_PROXY_FAILED",
      message: error instanceof Error ? error.message : String(error),
      backend_url: backendBaseUrl,
    })
  }

  res.statusCode = upstream.status
  upstream.headers.forEach((value, key) => {
    if (HOP_BY_HOP_HEADERS.has(String(key).toLowerCase())) return
    res.setHeader(key, value)
  })
  const body = Buffer.from(await upstream.arrayBuffer())
  res.end(body)
}
