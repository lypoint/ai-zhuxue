// First-party timings only; no URLs, content, account IDs, tokens or persistent browser ID.
export type PerformanceOperation = "chat_stream" | "image_upload" | "image_read";
type Result = "success" | "error" | "cancelled" | "incomplete";
export type PerformancePayload = {trace_id:string; operation:PerformanceOperation; result:Result; metrics:Record<string,number>};
export class PerformanceAttempt {
  id = crypto.randomUUID();
  metrics: Record<string,number> = {};
  started = performance.now();
  result: Result = "incomplete";
  constructor(public operation:PerformanceOperation, private send:(payload:PerformancePayload)=>void) {}
  mark(name:string) { this.metrics[name] ??= performance.now() - this.started; }
  headers(response:Response) {
    const id = response.headers.get("X-Trace-Id");
    if (id && /^[0-9a-f-]{36}$/i.test(id)) this.id = id as `${string}-${string}-${string}-${string}-${string}`;
    this.mark("browser_headers_ms");
    const match = response.headers.get("Server-Timing")?.match(/(?:^|,)\s*edge_upstream_headers;dur=([\d.]+)/);
    if (match && Number.isFinite(Number(match[1]))) this.metrics.edge_upstream_headers_ms = Number(match[1]);
  }
  finish() {
    this.mark("browser_total_ms");
    try { this.send({trace_id:this.id, operation:this.operation, result:this.result, metrics:this.metrics}); } catch { /* Optional observation. */ }
  }
}

export function startPerformance(operation:PerformanceOperation, send:(payload:PerformancePayload)=>void) {
  try { return new PerformanceAttempt(operation, send); } catch { return undefined; }
}

export function observeImagePerformance(send:(payload:PerformancePayload)=>void) {
  if (typeof PerformanceObserver === "undefined") return () => {};
  try {
    const observer = new PerformanceObserver(list => {
      for (const entry of list.getEntries() as PerformanceResourceTiming[]) {
        // Resource names are used only locally to classify the operation.
        if (!entry.name.startsWith(location.origin + "/api/browser/student/media/")) continue;
        const id = entry.serverTiming?.find(timing=>timing.name === "trace")?.description
          || new URL(entry.name).searchParams.get("_trace");
        if (!id || !/^[0-9a-f-]{36}$/i.test(id)) continue;
        const edge = entry.serverTiming?.find(timing=>timing.name === "edge_upstream_headers");
        const metrics:Record<string,number> = {browser_total_ms:entry.duration};
        if (entry.responseStart > 0) metrics.browser_headers_ms = entry.responseStart - entry.startTime;
        if (edge) metrics.edge_upstream_headers_ms = edge.duration;
        // Resource completion is not proof that the image decoded or painted successfully.
        try { send({trace_id:id, operation:"image_read", result:"incomplete", metrics}); } catch { /* Optional observation. */ }
      }
    });
    observer.observe({type:"resource"});
    return () => observer.disconnect();
  } catch { return () => {}; }
}
