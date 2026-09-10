export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

export async function fetchHistory() {
  const res = await fetch(`${API_BASE}/history/`);
  return res.json();
}

export async function fetchDetail(id) {
  const res = await fetch(`${API_BASE}/history/${id}/`);
  return res.json();
}

export async function deleteQuestion(id) {
  return fetch(`${API_BASE}/history/${id}/delete/`, { method: "DELETE" });
}

export async function clearHistory() {
  return fetch(`${API_BASE}/history/clear/`, { method: "DELETE" });
}

export async function togglePin(id) {
  return fetch(`${API_BASE}/history/${id}/pin/`, { method: "PATCH" });
}

/**
 * Opens an SSE connection that streams the live comparison:
 * start -> model_started -> model_chunk* -> model_finished (per model)
 * -> judge_started -> complete
 */
export function streamAsk(question, handlers) {
  const url = `${API_BASE}/ask/stream/?question=${encodeURIComponent(question)}`;
  const es = new EventSource(url);

  ["start", "model_started", "model_chunk", "model_finished", "judge_started", "complete", "error"].forEach(
    (event) => {
      if (handlers[event]) {
        es.addEventListener(event, (e) => handlers[event](JSON.parse(e.data)));
      }
    }
  );

  return es;
}
