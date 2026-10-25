import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "./api";
import { ResourceState, useAction, useResource } from "./ui";

type Catalog = { enabled: boolean; items: { product_code: string; seat_count: number; amount: string; currency: string }[] };

export default function CreemTest({ reload, provider }: { reload: () => void; provider?: string }) {
  const { t, i18n } = useTranslation();
  const catalog = useResource<Catalog>("/parent/creem/catalog");
  const { run, busy } = useAction();
  const [pending, setPending] = useState(() => sessionStorage.getItem("creem-test-checkout") || "");
  const returned = useRef(false);
  const verify = async (id: string) => {
    await api("/parent/creem/verify", "POST", { checkout_id: id });
    sessionStorage.removeItem("creem-test-checkout"); setPending(""); reload();
  };
  useEffect(() => {
    if (!catalog.data?.enabled || returned.current) return;
    const params = new URLSearchParams(location.search);
    if (!params.has("creem_return")) return;
    returned.current = true;
    const id = params.get("checkout_id") || pending;
    if (id) { sessionStorage.setItem("creem-test-checkout", id); setPending(id); void run(() => verify(id)); }
    // Success query parameters only trigger a server check; they never grant access.
    history.replaceState(null, "", location.pathname);
  }, [catalog.data?.enabled, pending, run]);
  if (!catalog.data?.enabled) return catalog.error ? <ResourceState {...catalog} retry={catalog.reload} /> : null;
  const navigate = (url: string, checkout: boolean) => {
    const parsed = new URL(url);
    if (parsed.protocol !== "https:" || !["creem.io", "www.creem.io"].includes(parsed.host) ||
        !(checkout ? parsed.pathname.startsWith("/test/") : parsed.pathname.startsWith("/test/my-orders/"))) throw new Error("Invalid Creem test URL.");
    location.assign(parsed.href);
  };
  return <section className="panel">
    <h2>Creem Test Mode</h2>
    <p className="notice">Test payments only. No real money is charged. These USD amounts are test prices, not final pricing.</p>
    {provider === "creem_test" ? <button className="button" disabled={busy} onClick={() => void run(async () => {
      const result = await api<{ url: string }>("/parent/creem/manage"); navigate(result.url, false);
    })}>{t("cancel")}</button> : catalog.data.items.map(item => <button className="button" key={item.product_code} disabled={busy} onClick={() => void run(async () => {
      const result = await api<{ checkout_id: string; url: string }>("/parent/creem/checkout", "POST", { product_code: item.product_code });
      sessionStorage.setItem("creem-test-checkout", result.checkout_id); setPending(result.checkout_id); navigate(result.url, true);
    })}>
      {item.seat_count} · {t("seats")} · {new Intl.NumberFormat(i18n.language, { style: "currency", currency: item.currency }).format(Number(item.amount) / 100)} / month
    </button>)}
    {pending && <button className="button secondary" disabled={busy} onClick={() => void run(() => verify(pending))}>{t("retry")}</button>}
  </section>;
}
