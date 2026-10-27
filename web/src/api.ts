import { startPerformance, type PerformanceAttempt, type PerformancePayload } from "./request-performance";
export const ROLE = __WEB_ROLE__;
export const ROOT = `/api/browser/${ROLE}`;
function recordResult(path: string, method: string, status: number) {
  if (__WEB_ROLE__ === "parent") window.dispatchEvent(new CustomEvent("parent-api-result", {
    detail: { path, method, status },
  }));
}
let csrf = "";
export function setCSRF(value: string) {
  csrf = value;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

export async function request(
  path: string,
  init: RequestInit = {},
  timing?: PerformanceAttempt,
): Promise<Response> {
  const headers = new Headers(init.headers);
  if (timing) headers.set("X-Trace-Id", timing.id);
  if (!["GET", "HEAD"].includes(init.method || "GET"))
    headers.set("X-CSRF-Token", csrf);
  if (init.body && typeof init.body === "string")
    headers.set("Content-Type", "application/json");
  let response: Response;
  try {
    response = await fetch(ROOT + path, {
      ...init,
      headers,
      credentials: "same-origin",
      cache: "no-store",
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError")
      throw error;
    recordResult(path, init.method || "GET", 0);
    throw new ApiError(
      0,
      "Network unavailable. Please check the latest state before retrying.",
    );
  }
  timing?.headers(response);
  recordResult(path, init.method || "GET", response.status);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    if (
      response.status === 401 &&
      path !== "/session" &&
      !path.endsWith("/login")
    )
      window.dispatchEvent(new Event("session-expired"));
    const detail =
      typeof body.detail === "string"
        ? body.detail
        : "Please check the form and try again.";
    throw new ApiError(response.status, detail);
  }
  return response;
}

export function browserEvent(name: string, properties: Record<string, string | number> = {}) {
  if (!csrf) return;
  try {
    void request("/events", {method:"POST", keepalive:true,
      body:JSON.stringify({id:crypto.randomUUID(), name, properties})}).catch(() => {});
  } catch { /* Telemetry must never interrupt business actions. */ }
}

export function sendPerformance(payload: PerformancePayload) {
  if (ROLE !== "student" || !csrf) return;
  void request("/performance", {method:"POST", keepalive:true, body:JSON.stringify(payload)}).catch(() => {});
}

export async function api<T = unknown>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await request("/api" + path, {
    method,
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  return response.json();
}

export async function browser<T = unknown>(
  path: string,
  method = "GET",
  data?: unknown,
): Promise<T> {
  const response = await request(path, {
    method,
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  return response.json();
}

export async function stream(
  body: unknown,
  signal: AbortSignal,
  event: (name: string, data: Record<string, unknown>) => void,
) {
  const timing = ROLE === "student" ? startPerformance("chat_stream", sendPerformance) : undefined;
  try {
    const response = await request("/api/chat/stream", {
      method: "POST",
      body: JSON.stringify(body),
      signal,
    }, timing);
    if (!response.body)
      throw new ApiError(503, "Streaming is unavailable. Please retry.");
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "",
      completed = false;
    try {
      while (true) {
        const { value, done } = await reader.read();
        buffer += decoder.decode(value, { stream: !done }).replace(/\r/g, "");
        let split: number;
        while ((split = buffer.indexOf("\n\n")) >= 0) {
          const packet = buffer.slice(0, split);
          buffer = buffer.slice(split + 2);
          const name = packet
            .split("\n")
            .find((line) => line.startsWith("event:"))
            ?.slice(6)
            .trim();
          const data = packet
            .split("\n")
            .filter((line) => line.startsWith("data:"))
            .map((line) => line.slice(5).trimStart())
            .join("\n");
          if (name && data) {
            const payload = JSON.parse(data);
            if ((name === "delta" || name === "replace") && payload.text) timing?.mark("browser_first_delta_ms");
            if (name === "done") { timing?.mark("browser_done_ms"); if (timing) timing.result = "success"; }
            event(name, payload);
            if (name === "done") completed = true;
            if (name === "error")
              throw new ApiError(
                503,
                String(
                  payload.message ||
                    "The answer could not be completed. Please retry.",
                ),
              );
          }
        }
        if (done) break;
      }
      if (!completed)
        throw new ApiError(
          503,
          "The connection ended before the answer finished. Please retry.",
        );
    } finally {
      reader.releaseLock();
    }
  } catch (error) {
    if (timing) timing.result = error instanceof DOMException && error.name === "AbortError" ? "cancelled" : "error";
    throw error;
  } finally {
    timing?.finish();
  }
}

export type Session = {
  role: "parent" | "student";
  id: number;
  family_id: number;
  nickname: string;
  timezone: string | null;
  grade_band: string | null;
  csrf_token: string;
};
export type Child = {
  id: number;
  nickname: string;
  grade_band: string;
  active: boolean;
  seat_status: string;
  current_device: { name: string; last_seen_at: string | null } | null;
  fence_settings: { fence_level: string; forbidden_words: string[] };
  learning_settings: Pick<FamilySettings, "daily_message_cap" | "daily_minutes_cap" | "quiet_enabled" | "quiet_start" | "quiet_end" | "notify_fence">;
};
export type FamilySettings = {
  daily_message_cap: number;
  quiet_enabled: boolean;
  quiet_start: number;
  quiet_end: number;
  daily_minutes_cap: number;
  review_enabled: boolean;
  notify_fence: boolean;
};
export type Family = {
  guardian: { id: number; nickname: string };
  timezone: string | null;
  students: Child[];
  settings: FamilySettings;
};
export type ImageBlock = {
  type: string;
  asset_id?: string;
  caption?: string;
  width?: number;
  height?: number;
};
export type Message = {
  id: number;
  role: string;
  content: string;
  content_blocks: ImageBlock[];
  fence_action: string | null;
  created_at: string;
  teacher_name?: string;
  teacher_avatar_url?: string;
  image_job?: ImageJob | null;
};
export type ImageJob = {
  id: number;
  state: string;
  error: string;
  asset_id?: string;
  content_blocks?: ImageBlock[];
};
export type Conversation = {
  id?: number;
  conversation_id?: number;
  title: string;
  pinned?: boolean;
  teacher_id: number | null;
  teacher_name: string;
  student_deleted?: boolean;
  message_count?: number;
  last_time?: string;
  created_at?: string;
};
export type Favorite = {
  id: number;
  content: string;
  content_blocks: ImageBlock[];
  conversation_id: number | null;
  message_id?: number | null;
  created_at: string;
};
export type Stats = {
  today: {
    minutes: number;
    questions: number;
    blocked?: number;
    quota_used_seconds?: number;
  };
  week: { minutes: number; questions: number; active_days: number };
  favorites?: number;
};
export type Grade = {
  id: number;
  subject: string;
  title: string;
  exam_date: string;
  term: string;
  score: number;
  max_score: number;
  grade_type: string;
  note: string;
  deleted: boolean;
  current_version?: number;
};
