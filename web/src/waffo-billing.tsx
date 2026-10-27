import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "./api";
import { ResourceState, useAction, useResource } from "./ui";
import { track } from "./parent-analytics";

type Catalog = { enabled: boolean; test_mode: boolean; has_subscription?: boolean; items: { product_code: string; seat_count: number; amount: string; currency: string }[] };

export default function WaffoBilling({ reload, provider }: { reload: () => void; provider?: string }) {
  const { t, i18n } = useTranslation();
  const catalog = useResource<Catalog>("/parent/waffo/catalog");
  const { run, busy } = useAction();
  const [pending, setPending] = useState(() => sessionStorage.getItem("waffo-checkout") || "");
  const returned = useRef(false);
  const verify = async (reference: string) => {
    await api("/parent/waffo/verify", "POST", { reference });
    sessionStorage.removeItem("waffo-checkout"); setPending(""); reload();
  };
  useEffect(() => {
    if (!catalog.data?.enabled || returned.current) return;
    const reference = new URLSearchParams(location.search).get("waffo_return");
    if (!reference) return;
    returned.current = true;
    sessionStorage.setItem("waffo-checkout", reference); setPending(reference);
    // A return URL requests verification; it never grants subscription rights.
    history.replaceState(null, "", location.pathname);
    void run(() => verify(reference));
  }, [catalog.data?.enabled, run]);
  if (!catalog.data?.enabled) return catalog.error ? <ResourceState {...catalog} retry={catalog.reload} /> : null;
  const navigate = (url: string, checkout: boolean) => {
    const parsed = new URL(url);
    const allowed = checkout
      ? parsed.host === "pancake.waffo.ai" && /^\/store\/[^/]+\/checkout\/cs_[A-Za-z0-9_-]+$/.test(parsed.pathname) ||
        parsed.host === "checkout.waffo.ai" && /^\/[^/]+\/checkout\/cs_[A-Za-z0-9_-]+$/.test(parsed.pathname)
      : parsed.host === "pancake.waffo.ai" && parsed.pathname.startsWith("/consumer/portal/");
    if (parsed.protocol !== "https:" || !allowed) throw new Error(t("verificationFailed"));
    if (checkout) void track("checkout_open", { provider: "waffo" });
    location.assign(parsed.href);
  };
  return <section className="panel">
    <h2>{t("subscription")}</h2>
    {catalog.data.test_mode && <p className="notice">{t("testPayments")}</p>}
    {(provider === "waffo" || catalog.data.has_subscription) && <button className="button" disabled={busy} onClick={() => void run(async () => {
      const result = await api<{ url: string }>("/parent/waffo/manage"); navigate(result.url, false);
    })}>{t("manageSubscription")}</button>}
    {provider !== "waffo" && catalog.data.items.map(item => <button className="button" key={item.product_code} disabled={busy} onClick={() => void run(async () => {
      void track("begin_checkout", { provider: "waffo", seat_count: item.seat_count });
      try {
        const result = await api<{ reference: string; url: string }>("/parent/waffo/checkout", "POST", { product_code: item.product_code });
        sessionStorage.setItem("waffo-checkout", result.reference); setPending(result.reference);
        navigate(result.url, true);
      } catch (error) { void track("checkout_error", { provider: "waffo" }); throw error; }
    })}>
      {new Intl.NumberFormat(i18n.language).format(item.seat_count)} · {t("seats")} · {new Intl.NumberFormat(i18n.language, { style: "currency", currency: item.currency }).format(Number(item.amount))} · {t("monthlyBilling")}
    </button>)}
    {pending && <button className="button secondary" disabled={busy} onClick={() => void run(() => verify(pending))}>{t("retry")}</button>}
    <button className="button secondary" disabled={busy} onClick={() => void run(async () => {
      await api("/parent/waffo/refresh", "POST"); reload();
    })}>{t("refreshSubscription")}</button>
  </section>;
}
