/**
 * The one place the frontend talks to the API.
 *
 * Centralising fetch() here means JSON encoding, error shapes and cookie
 * handling are solved once rather than re-invented in every feature.
 */

/** An error carrying the HTTP status and a message fit to show a user. */
export class ApiError extends Error {
  constructor(status, detail) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

/**
 * FastAPI reports errors in two different shapes: a plain string for the
 * ones we raise ourselves, and a list of per-field objects for validation
 * failures. Normalise both into one readable sentence.
 */
function readDetail(body, status) {
  const detail = body?.detail;

  if (typeof detail === "string") {
    return detail;
  }

  if (Array.isArray(detail) && detail.length > 0) {
    const [first] = detail;
    const field = first.loc?.at(-1);
    const message = first.msg ?? "is not valid";
    return field ? `${field}: ${message}` : message;
  }

  return `Something went wrong (HTTP ${status}).`;
}

/**
 * Call a JSON endpoint.
 *
 * @param {string} path     e.g. "/api/auth/login"
 * @param {object} [options]
 * @param {string} [options.method="GET"]
 * @param {object} [options.body]  serialised to JSON when present
 * @returns {Promise<object|null>} parsed body, or null for 204 responses
 * @throws {ApiError} when the response status is not 2xx
 */
export async function apiFetch(path, { method = "GET", body, signal } = {}) {
  const response = await fetch(path, {
    method,
    headers: body ? { "Content-Type": "application/json" } : {},
    body: body ? JSON.stringify(body) : undefined,
    // Send the session cookie. Same-origin is already the default, but
    // stating it makes the dependency on the cookie explicit.
    credentials: "same-origin",
    // Lets a caller cancel an in-flight request (used to drop stale
    // searches). Undefined when not supplied, which fetch simply ignores.
    signal,
  });

  // 204 No Content (our logout) has no body to parse.
  if (response.status === 204) {
    return null;
  }

  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new ApiError(response.status, readDetail(data, response.status));
  }

  return data;
}
