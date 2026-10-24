import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api } from "./api";
import { ResourceState, useAction, useResource } from "./ui";

type Catalog = {
  enabled: boolean;
  client_token?: string;
  items: { product_code: string; seat_count: number; amount: string; currency: string; name: string }[];
};
type Paddle = {
  Environment: { set: (environment: "sandbox") => void };
  Initialize: (options: { token: string; eventCallback: (event: { name: string; data?: { transaction_id?: string } }) => void }) => void;
  Checkout: { open: (options: { transactionId: string }) => void };
};
declare global { interface Window { Paddle?: Paddle } }

let sdk: Promise<Paddle> | undefined;
let initialized = false;
let onCompleted: (transactionId?: string) => void = () => {};
function loadPaddle() {
  if (window.Paddle) return Promise.resolve(window.Paddle);
  if (!sdk) sdk = new Promise<Paddle>((resolve, reject) => {
    const script = document.createElement("script");
    script.src = "https://cdn.paddle.com/paddle/v2/paddle.js";
    script.onload = () => window.Paddle ? resolve(window.Paddle) : reject(new Error("Paddle did not load."));
    script.onerror = () => { script.remove(); sdk = undefined; reject(new Error("Paddle could not load. Please retry.")); };
    document.head.append(script);
  });
  return sdk;
}

export default function PaddleSandbox({ reload, provider }: { reload: () => void; provider?: string }) {
  const { t, i18n } = useTranslation();
  const catalog = useResource<Catalog>("/parent/paddle/catalog");
  const { run, busy } = useAction();
  const [pending, setPending] = useState(() => sessionStorage.getItem("paddle-sandbox-transaction") || "");
  const [confirming, setConfirming] = useState(false);
  const linkOpened = useRef(false);
  useEffect(() => {
    if (!confirming || !pending) return;
    let current = true;
    let timer: ReturnType<typeof setTimeout>;
    let tries = 0;
    const verify = async () => {
      try {
        await api("/parent/paddle/verify", "POST", { transaction_id: pending });
        if (!current) return;
        sessionStorage.removeItem("paddle-sandbox-transaction");
        setPending(""); setConfirming(false); reload();
      } catch {
        if (!current) return;
        if (++tries < 10) timer = setTimeout(verify, 1500);
        else setConfirming(false);
      }
    };
    void verify();
    return () => { current = false; clearTimeout(timer); };
  }, [confirming, pending, reload]);
  const clientToken = catalog.data?.client_token;
  const show = useCallback(async (transactionId: string) => {
    if (!clientToken) throw new Error("Sandbox checkout is unavailable.");
    const paddle = await loadPaddle();
    onCompleted = (transactionId) => {
      if (transactionId) setPending(transactionId);
      setConfirming(true);
    };
    if (!initialized) {
      paddle.Environment.set("sandbox");
      paddle.Initialize({ token: clientToken, eventCallback: (event) => {
        if (event.name === "checkout.completed") onCompleted(event.data?.transaction_id);
      } });
      initialized = true;
    }
    sessionStorage.setItem("paddle-sandbox-transaction", transactionId);
    setPending(transactionId);
    paddle.Checkout.open({ transactionId });
  }, [clientToken]);
  useEffect(() => {
    const transactionId = new URLSearchParams(location.search).get("_ptxn");
    if (!clientToken || !transactionId || linkOpened.current) return;
    linkOpened.current = true;
    void run(async () => {
      const result = await api<{ transaction_id: string; status: string }>("/parent/paddle/resume", "POST", { transaction_id: transactionId });
      if (result.status === "completed") {
        setPending(result.transaction_id);
        setConfirming(true);
      } else await show(result.transaction_id);
      const url = new URL(location.href);
      url.searchParams.delete("_ptxn");
      history.replaceState(null, "", url.pathname + url.search + url.hash);
    });
  }, [clientToken, run, show]);
  if (!catalog.data?.enabled) return catalog.error ? <ResourceState {...catalog} retry={catalog.reload} /> : <p className="notice">{t("noPayment")}</p>;
  const open = async (product_code: string) => {
    const result = await api<{ transaction_id: string }>("/parent/paddle/checkout", "POST", { product_code });
    await show(result.transaction_id);
  };
  return <section className="panel">
    <h2>Paddle Sandbox</h2>
    <p className="notice">Test payments only. No real money is charged. Monthly subscription; the final currency and tax are shown at checkout.</p>
    {provider === "paddle_sandbox" ? <button className="button" disabled={busy} onClick={() => void run(async () => {
      const result = await api<{ url: string }>("/parent/paddle/manage");
      const url = new URL(result.url);
      if (url.protocol !== "https:" || url.hostname !== "sandbox-customer-portal.paddle.com") throw new Error("Invalid Sandbox portal URL.");
      window.location.assign(url.href);
    })}>{t("cancel")}</button> : catalog.data.items.map(item => <button className="button" key={item.product_code} disabled={busy || confirming} onClick={() => void run(() => open(item.product_code))}>
      {item.seat_count} · {t("seats")} · {new Intl.NumberFormat(i18n.language, { style: "currency", currency: item.currency }).format(Number(item.amount) / 100)} / month
    </button>)}
    {pending && <button className="button secondary" disabled={confirming} onClick={() => setConfirming(true)}>{confirming ? t("pending") : t("retry")}</button>}
  </section>;
}
