/**
 * Extracts a human-readable error message from Axios errors.
 * Handles FastAPI validation errors (array of {type, loc, msg, input, ctx})
 * and plain string detail messages.
 */
export function getErrorMessage(err: unknown, fallback = "Something went wrong"): string {
  const detail = (err as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;

  if (!detail) return fallback;

  // FastAPI 422: detail is an array of Pydantic validation errors
  if (Array.isArray(detail)) {
    return detail
      .map((item: unknown) => {
        if (typeof item === "object" && item !== null && "msg" in item) {
          const loc = "loc" in item && Array.isArray((item as { loc: unknown[] }).loc)
            ? (item as { loc: string[] }).loc.slice(1).join(".")
            : null;
          const msg = (item as { msg: string }).msg;
          return loc ? `${loc}: ${msg}` : msg;
        }
        return String(item);
      })
      .join("; ");
  }

  if (typeof detail === "string") return detail;
  return fallback;
}
