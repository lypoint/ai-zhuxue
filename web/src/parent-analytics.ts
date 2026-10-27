import { browserEvent } from "./api";
// Fixed vocabulary: never pass API bodies, IDs, URLs, names or learning content.
const events = ["page_view", "login_start", "login", "sign_up", "trial_start",
  "child_create", "bind_code_create", "child_connected_observed", "view_subscription", "begin_checkout",
  "checkout_open", "checkout_closed", "checkout_error", "subscription_verify", "subscription_manage"] as const;
export type AnalyticsEvent = typeof events[number];
type Provider = "google" | "waffo";
type Parameters = { result?: "success" | "failure"; provider?: Provider; seat_count?: number; status?: number };
const pages = ["home", "children", "activity", "schedule", "favorites", "learning", "grades", "assessments", "notifications", "subscription", "settings", "other"] as const;
export function analyticsPage(path: string): string {
  const first = path.split(/[?#]/, 1)[0].split("/")[1] || "home";
  return (pages as readonly string[]).includes(first) ? first : "other";
}
const consentStorageKey = "parent-analytics-choice";
const config = __WEB_ROLE__ === "parent" ? __PARENT_FIREBASE_CONFIG__ : null;
export const analyticsConfigured = !!(config?.apiKey && config.appId && config.projectId && /^G-[A-Z0-9]+$/.test(config.measurementId));
export function analyticsConsent(): boolean | null {
  if (memoryConsent !== null) return memoryConsent;
  try {
    const value = localStorage.getItem(consentStorageKey);
    return value === "granted" ? true : value === "denied" ? false : null;
  } catch { return memoryConsent; }
}
let memoryConsent: boolean | null = null;
type Sink = { log: (event: string, parameters: Record<string, string | number>) => void; consent: (granted: boolean) => void };
let sink: Sink | null = null;
let loading: Promise<Sink | null> | undefined;
const granted = () => analyticsConfigured && analyticsConsent() === true;
function disabled(value: boolean) {
  if (config) (window as unknown as Record<string, unknown>)[`ga-disable-${config.measurementId}`] = value;
}
function clearCookies() {
  const domains = location.hostname.split(".");
  const names = document.cookie.split(";").map(value => value.trim().split("=", 1)[0]).filter(name => /^_ga(?:_|$)|^_gid$|^_gat/.test(name));
  for (const name of names) {
    document.cookie = `${name}=; Max-Age=0; Path=/`;
    for (let i = 0; i < domains.length - 1; i++)
      document.cookie = `${name}=; Max-Age=0; Path=/; Domain=${domains.slice(i).join(".")}`;
  }
}
export function setAnalyticsConsent(value: boolean) {
  memoryConsent = value;
  try { localStorage.setItem(consentStorageKey, value ? "granted" : "denied"); } catch { /* In-memory choice still applies. */ }
  applyConsent();
  window.dispatchEvent(new Event("parent-analytics-consent"));
}
function applyConsent() {
  const value = granted();
  disabled(!value);
  try { sink?.consent(value); } catch { /* Privacy choice still applies if the SDK fails. */ }
  if (!value) {
    try { clearCookies(); } catch { /* Cookies may be blocked by the browser. */ }
  }
}
async function ready(): Promise<Sink | null> {
  if (!granted() || !config) return null;
  loading ??= import("./firebase-analytics").then(module => module.createAnalytics(config, granted))
    .then(value => { sink = value; if (!value) loading = undefined; applyConsent(); return value; })
    .catch(() => { loading = undefined; return null; });
  return loading;
}
export async function track(event: AnalyticsEvent, params: Parameters = {}, page?: string) {
  // Do not queue or replay any activity that happened before consent.
  if (!granted() || !(events as readonly string[]).includes(event)) return;
  try {
    // Family linkage stays on our server; GA receives only the existing fixed vocabulary.
    if (["page_view", "view_subscription", "begin_checkout", "checkout_open", "checkout_closed", "checkout_error", "subscription_verify", "subscription_manage"].includes(event)) {
      const properties: Record<string, string | number> = {};
      if (params.provider && ["google", "waffo"].includes(params.provider)) properties.provider = params.provider;
      if (params.result === "success" || params.result === "failure") properties.result = params.result;
      if (Number.isInteger(params.seat_count) && params.seat_count! > 0 && params.seat_count! <= 1000) properties.seat_count = params.seat_count!;
      properties.page = page && (pages as readonly string[]).includes(page) ? page : analyticsPage(location.pathname);
      browserEvent(event, properties);
    }
    const target = sink || await ready();
    if (!target || !granted()) return;
    const safe: Record<string, string | number> = {};
    if (params.result === "success" || params.result === "failure") safe.result = params.result;
    if (["google", "waffo"].includes(params.provider || "")) safe.provider = params.provider!;
    if (Number.isInteger(params.seat_count) && params.seat_count! > 0 && params.seat_count! <= 1000) safe.seat_count = params.seat_count!;
    if (Number.isInteger(params.status) && params.status! >= 0 && params.status! <= 599) safe.status = params.status!;
    const name = page && (pages as readonly string[]).includes(page) ? page : analyticsPage(location.pathname);
    target.log(event, { ...safe, page_name: name, page_location: `${location.origin}/${name === "home" ? "" : name}`,
      page_title: "AI StudyNest Parent", page_referrer: "" });
  } catch { /* Analytics must not interrupt sign-in, learning or checkout. */ }
}
if (__WEB_ROLE__ === "parent") {
  disabled(!granted());
  window.addEventListener("storage", event => {
    if (event.key === consentStorageKey || event.key === null) {
      memoryConsent = null;
      applyConsent();
      window.dispatchEvent(new Event("parent-analytics-consent"));
    }
  });
  window.addEventListener("parent-api-result", event => {
    const { path, method, status } = (event as CustomEvent<{ path: string; method: string; status: number }>).detail;
    const result = status >= 200 && status < 300 ? "success" : "failure";
    if (method === "POST" && path === "/api/parent/students") {
      void track("child_create", { result, status });
      if (result === "success") void track("bind_code_create", { result, status });
    }
    if (method === "POST" && /^\/api\/parent\/students\/\d+\/rebind-code$/.test(path)) void track("bind_code_create", { result, status });
    const payment = path.match(/^\/api\/parent\/(waffo)\/(verify|manage)$/);
    if (payment && ((method === "POST" && payment[2] === "verify") || (method === "GET" && payment[2] === "manage")))
      void track(payment[2] === "verify" ? "subscription_verify" : "subscription_manage", {
        result, status, provider: "waffo",
      });
  });
}
