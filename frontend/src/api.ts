export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code = "request_failed",
    public diagnosticId?: string,
  ) {
    super(message);
  }
}

export async function api<T = unknown>(
  path: string,
  data?: unknown,
): Promise<T> {
  try {
    let response: Response;
    try {
      response = await fetch("/api/" + path, {
        ...(data === undefined
          ? {}
          : {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "X-Study-Request": "1",
                ...(window.__PRACTICE_ROOM_BUILD__
                  ? { "X-Study-Build": window.__PRACTICE_ROOM_BUILD__ }
                  : {}),
              },
              body: JSON.stringify(data),
            }),
        signal: AbortSignal.timeout(20000),
      });
    } catch {
      throw new ApiError(
        "The app connection was interrupted. Keep this page open and reopen Start Study, or download your work.",
        0,
        "connection_error",
      );
    }
    let result;
    try {
      result = await response.json();
    } catch {
      throw new ApiError(
        `The local app returned an invalid response (HTTP ${response.status}). Reconnect the app or download your work.`,
        response.status,
        "invalid_response",
      );
    }
    if (!response.ok) {
      throw new ApiError(
        typeof result.detail === "string"
          ? result.detail
          : "Check the entered values and try again.",
        response.status,
        result.code,
        result.diagnostic_id,
      );
    }
    return result as T;
  } catch (error) {
    // A timeout or broken response may happen after commit. Reconcile the durable
    // receipt before asking the learner to retry an already completed session.
    if (
      (path === "practice/finish" || path === "action/finish") &&
      error instanceof ApiError &&
      (error.status === 0 ||
        error.status >= 500 ||
        error.code === "invalid_response") &&
      data &&
      typeof data === "object" &&
      "session_id" in data
    ) {
      try {
        return await api<T>(
          "completions/" + encodeURIComponent(String(data.session_id)),
        );
      } catch {
        /* Preserve the original error and browser draft. */
      }
    }
    throw error;
  }
}
export function formatTime(seconds: number) {
  const n = Math.max(0, Math.floor(seconds));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}
export function sessionProgress(seconds: number, budgetMinutes: number) {
  if (
    !Number.isFinite(seconds) ||
    !Number.isFinite(budgetMinutes) ||
    budgetMinutes <= 0
  )
    return 0;
  return Math.min(
    100,
    Math.max(0, Math.round((seconds / (budgetMinutes * 60)) * 100)),
  );
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
