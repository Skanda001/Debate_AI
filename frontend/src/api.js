export const API_BASE = import.meta.env.VITE_API_BASE || "http://127.0.0.1:8000/api";

const TOKEN_KEY = "debate_ai_token";

export function getAuthToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setAuthToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export function removeAuthToken() {
  localStorage.removeItem(TOKEN_KEY);
}

function authHeaders(extra = {}) {
  const token = getAuthToken();
  const headers = { ...extra };
  if (token) {
    headers["Authorization"] = `Token ${token}`;
  }
  return headers;
}

/* ==================== Auth Endpoints ==================== */

export async function apiRegister(username, email, password) {
  const res = await fetch(`${API_BASE}/auth/register/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, email, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Failed to register");
  }
  if (data.token) {
    setAuthToken(data.token);
  }
  return data;
}

export async function apiLogin(username, password) {
  const res = await fetch(`${API_BASE}/auth/login/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data.error || "Failed to login");
  }
  if (data.token) {
    setAuthToken(data.token);
  }
  return data;
}

export async function apiGetMe() {
  const token = getAuthToken();
  if (!token) return null;
  try {
    const res = await fetch(`${API_BASE}/auth/me/`, {
      headers: authHeaders(),
    });
    if (!res.ok) {
      if (res.status === 401) {
        removeAuthToken();
      }
      return null;
    }
    const data = await res.json();
    return data.user;
  } catch (e) {
    console.error("Failed to fetch user profile", e);
    return null;
  }
}

export async function apiLogout() {
  try {
    await fetch(`${API_BASE}/auth/logout/`, {
      method: "POST",
      headers: authHeaders(),
    });
  } catch (e) {
    console.error("Logout error", e);
  } finally {
    removeAuthToken();
  }
}

/* ==================== Question / History Endpoints ==================== */

export async function fetchHistory() {
  const res = await fetch(`${API_BASE}/history/`, {
    headers: authHeaders(),
  });
  return res.json();
}

export async function fetchDetail(id) {
  const res = await fetch(`${API_BASE}/history/${id}/`, {
    headers: authHeaders(),
  });
  return res.json();
}

export async function deleteQuestion(id) {
  return fetch(`${API_BASE}/history/${id}/delete/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export async function clearHistory() {
  return fetch(`${API_BASE}/history/clear/`, {
    method: "DELETE",
    headers: authHeaders(),
  });
}

export async function togglePin(id) {
  return fetch(`${API_BASE}/history/${id}/pin/`, {
    method: "PATCH",
    headers: authHeaders(),
  });
}

/**
 * Opens an SSE connection that streams the live comparison:
 * start -> model_started -> model_chunk* -> model_finished (per model)
 * -> judge_started -> complete
 */
export function streamAsk(question, handlers, parentId = null) {
  let url = `${API_BASE}/ask/stream/?question=${encodeURIComponent(question)}`;
  const token = getAuthToken();
  if (token) {
    url += `&token=${encodeURIComponent(token)}`;
  }
  if (parentId) {
    url += `&parent_id=${encodeURIComponent(parentId)}`;
  }

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
