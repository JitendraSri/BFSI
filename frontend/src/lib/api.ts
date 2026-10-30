const BASE = process.env.NEXT_PUBLIC_API_URL ?? "";

function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem("token");
}

export async function apiFetch<T = unknown>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(options.headers ?? {}),
    },
  });
  if (res.status === 401) {
    localStorage.removeItem("token");
    window.location.href = "/login";
    throw new Error("Unauthorized");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error((data as { error?: string }).error ?? res.statusText);
  return data as T;
}

export async function apiStream(
  path: string,
  body: unknown,
  onStage: (label: string) => void,
  onToken: (text: string) => void,
  signal: AbortSignal
): Promise<{ answer: string; sources: unknown[]; conversation_id?: string }> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify(body),
    signal,
  });
  if (!res.ok || !res.body) {
    const data = await res.json().catch(() => ({}));
    throw new Error((data as { error?: string }).error ?? "Stream error");
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let done_payload: { answer: string; sources: unknown[]; conversation_id?: string } | null = null;

  const parseEvents = (chunk: string) => {
    buffer += chunk;
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      const name = /^event: (.+)$/m.exec(block)?.[1];
      const dataStr = /^data: (.*)$/m.exec(block)?.[1];
      if (!name || dataStr === undefined) continue;
      const payload = JSON.parse(dataStr);
      if (name === "stage") onStage(payload.label ?? payload.stage);
      else if (name === "token") onToken(payload.text ?? "");
      else if (name === "done") done_payload = payload;
      else if (name === "error") throw new Error(payload.error ?? "Stream error");
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    parseEvents(decoder.decode(value, { stream: true }));
  }

  if (!done_payload) throw new Error("Stream closed before answer finished.");
  return done_payload;
}
