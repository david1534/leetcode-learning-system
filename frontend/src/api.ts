export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T = any>(path: string, data?: unknown): Promise<T> {
  const response = await fetch(
    "/api/" + path,
    data === undefined
      ? {}
      : {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Study-Request": "1",
          },
          body: JSON.stringify(data),
        },
  );
  const result = await response.json();
  if (!response.ok)
    throw new ApiError(
      result.detail || "The request could not be completed.",
      response.status,
    );
  return result;
}
export function formatTime(seconds: number) {
  const n = Math.max(0, Math.floor(seconds));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}
export function metricLabel(
  metric: { passed: number; total: number } | undefined,
) {
  return metric?.total ? `${metric.passed} / ${metric.total}` : "Not measured";
}
// A server refresh must never replace a draft while it has unsaved edits.
export function reconcileDraft(local: string, remote: string, dirty: boolean) {
  return dirty ? local : remote;
}
