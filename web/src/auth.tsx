import { lazy, Suspense, useEffect, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { browser, ROLE, setCSRF, type Session } from "./api";
import {
  Brand,
  clearPrivateStorage,
  Field,
  formData,
  LanguagePicker,
  Legal,
  useAction,
} from "./ui";
import { tx } from "./i18n";

const GoogleSignIn =
  __WEB_ROLE__ === "parent" ? lazy(() => import("./google-sign-in")) : null;
export function Auth({
  children,
}: {
  children: (session: Session, refresh: () => Promise<void>) => ReactNode;
}) {
  const { t } = useTranslation();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [legal, setLegal] = useState<string | null>(null);
  const { busy, run } = useAction();
  const [config, setConfig] = useState<{ google_client_id: string } | null>(
    null,
  );
  const refresh = async () => {
    const data = await browser<Session>("/session");
    setCSRF(data.csrf_token);
    setSession(data);
  };
  useEffect(() => {
    void refresh()
      .catch((e) => {
        if (e.status === 401) clearPrivateStorage();
        else setError(e.message);
      })
      .finally(() => setLoading(false));
    const expired = () => {
      clearPrivateStorage();
      setSession(null);
      setCSRF("");
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, []);
  useEffect(() => {
    if (!session)
      void browser<{ google_client_id: string }>("/config")
        .then(setConfig)
        .catch((e) => setError(e.message));
  }, [session]);
  if (loading)
    return (
      <div className="loading-page" role="status">
        {t("loading")}
      </div>
    );
  if (session) return <>{children(session, refresh)}</>;
  return (
    <main className="auth-page">
      <header>
        <Brand />
        <LanguagePicker />
      </header>
      <div className="auth-layout">
        <section className="auth-story">
          <span className="eyebrow">
            {t(ROLE === "parent" ? "parentSpace" : "studentSpace")}
          </span>
          <h1>{t(ROLE === "parent" ? "welcome" : "connectHeading")}</h1>
          <p>{t(ROLE === "parent" ? "overviewHint" : "connectHint")}</p>
          <div className="auth-note">
            {t(ROLE === "parent" ? "parentVisibility" : "visibility")}
          </div>
        </section>
        <section className="auth-card">
          <h2>{t(ROLE === "parent" ? "signIn" : "connect")}</h2>
          {error && (
            <p className="notice error" role="alert">
              {tx(error)}
            </p>
          )}
          {ROLE === "parent" ? (
            <>
              <p>{t("googleHint")}</p>
              {config ? (
                config.google_client_id && GoogleSignIn ? (
                  <Suspense fallback={<p>{t("loading")}</p>}>
                    <GoogleSignIn
                      clientId={config.google_client_id}
                      onSuccess={refresh}
                    />
                  </Suspense>
                ) : (
                  <p className="notice">{t("googleUnavailable")}</p>
                )
              ) : (
                <p role="status">{t("loading")}</p>
              )}
              <button
                onClick={() => {
                  setError("");
                  void browser<{ google_client_id: string }>("/config")
                    .then(setConfig)
                    .catch((e) => setError(e.message));
                }}
              >
                {t("retry")}
              </button>
            </>
          ) : (
            <form
              onSubmit={(event) => {
                const data = formData(event);
                void run(async () => {
                  let installationId: string | null = null;
                  try {
                    installationId = localStorage.getItem(
                      "ai-learning-installation",
                    );
                  } catch {
                    /* Still connect with an ephemeral installation. */
                  }
                  if (!installationId) {
                    installationId = crypto.randomUUID();
                    try {
                      localStorage.setItem(
                        "ai-learning-installation",
                        installationId,
                      );
                    } catch {
                      /* No persistence in private mode. */
                    }
                  }
                  const result = await browser<{ csrf_token: string }>(
                    "/connect",
                    "POST",
                    {
                      bind_code: data.code.replace(/\s/g, "").toUpperCase(),
                      installation_id: installationId,
                      device_name: data.device_name,
                    },
                  );
                  setCSRF(result.csrf_token);
                  await refresh();
                });
              }}
            >
              <Field label={t("code")} hint={t("codeHelp")}>
                <input
                  name="code"
                  className="code-input"
                  aria-label={t("code")}
                  placeholder={t("codeHint")}
                  required
                  minLength={8}
                  maxLength={12}
                  autoComplete="off"
                  autoCapitalize="characters"
                  spellCheck={false}
                  pattern="[A-Fa-f0-9\s]{8,12}"
                />
              </Field>
              <Field label={t("deviceName")}>
                <input
                  name="device_name"
                  defaultValue={t("webBrowser")}
                  required
                  maxLength={100}
                />
              </Field>
              <button className="primary" disabled={busy}>
                {busy ? t("loading") : t("connect")}
              </button>
              <small>{t("expiredCode")}</small>
            </form>
          )}
          <footer className="actions">
            {["privacy", "help", "terms"].map((page) => (
              <button
                className="text-button"
                onClick={() => setLegal(page)}
                key={page}
              >
                {t(page)}
              </button>
            ))}
          </footer>
        </section>
      </div>
      {legal && <Legal page={legal} onClose={() => setLegal(null)} />}
    </main>
  );
}
