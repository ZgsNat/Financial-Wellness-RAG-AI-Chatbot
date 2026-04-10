import { api } from "@/lib/api";

export type InsightType =
  | "spending_pattern"
  | "mood_spending"
  | "budget_summary"
  | "wellness_suggestion";

export interface InsightResponse {
  id: string;
  user_id: string;
  type: InsightType;
  content: string;
  created_at: string;
}

export const insightApi = {
  list: () => api.get<InsightResponse[]>("/insights").then((r) => r.data),
};

export interface ApiKeyResponse {
  has_key: boolean;
  masked_key: string | null;
}

export const insightSettingsApi = {
  get: () => api.get<ApiKeyResponse>("/insights/settings").then((r) => r.data),
  save: (gemini_api_key: string) =>
    api.post<ApiKeyResponse>("/insights/settings", { gemini_api_key }).then((r) => r.data),
};

export const insightReindexApi = {
  reindexTransaction: (source_id: string, payload: Record<string, unknown>) =>
    api
      .post("/insights/reindex", { source_type: "transaction", source_id, payload })
      .then((r) => r.data),
};

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/**
 * Streams /insights/chat as SSE.
 * Receives chunks: { delta: "...", done?: false } or { done: true, sources: [] }
 */
export async function streamChat(
  question: string,
  token: string,
  onDelta: (text: string) => void,
  onDone: (sources: unknown[]) => void,
  onError: (msg: string) => void
) {
  const res = await fetch(`${API_URL}/insights/chat`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ question }),
  });

  if (!res.ok) {
    onError(`Error ${res.status}: ${res.statusText}`);
    return;
  }

  const reader = res.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      try {
        const ev = JSON.parse(raw);
        if (ev.error) {
          const friendlyMsg =
            ev.error === "quota_exceeded"
              ? "Đã hết quota Gemini hôm nay. Vui lòng thử lại vào ngày mai hoặc đổi API key."
              : ev.error === "service_unavailable"
              ? ev.message ?? "Gemini đang quá tải, vui lòng thử lại sau ít phút."
              : ev.message ?? ev.error;
          onError(friendlyMsg);
        } else if (ev.done) {
          onDone(ev.sources ?? []);
        } else if (ev.delta) {
          onDelta(ev.delta);
        }
      } catch {
        // ignore malformed chunk
      }
    }
  }
}
