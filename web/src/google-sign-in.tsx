import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { browser, setCSRF } from "./api";
import { useAction } from "./ui";
import { track } from "./parent-analytics";

declare global {
  interface Window {
    google?: {
      accounts: {
        id: {
          initialize: (options: {
            client_id: string;
            callback: (result: { credential: string }) => void;
            auto_select: boolean;
          }) => void;
          renderButton: (
            element: HTMLElement,
            options: Record<string, unknown>,
          ) => void;
        };
      };
    };
  }
}
export default function GoogleSignIn({
  clientId,
  onSuccess,
}: {
  clientId: string;
  onSuccess: () => Promise<void>;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const { t, i18n } = useTranslation();
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const { run, busy } = useAction();
  useEffect(() => {
    let current = true;
    const render = () => {
      if (!current || !ref.current || !window.google) return;
      window.google.accounts.id.initialize({
        client_id: clientId,
        auto_select: false,
        callback: (result) => {
          void run(async () => {
            void track("login_start", { provider: "google" });
            let response;
            try {
              response = await browser<{ csrf_token: string; is_new_user?: boolean }>(
                "/login",
                "POST",
                { id_token: result.credential },
              );
            } catch (error) {
              void track("login", { provider: "google", result: "failure" });
              throw error;
            }
            setCSRF(response.csrf_token);
            void track("login", { provider: "google", result: "success" });
            if (response.is_new_user) {
              void track("sign_up", { provider: "google" });
              void track("trial_start");
            }
            await onSuccess();
          });
        },
      });
      ref.current.replaceChildren();
      window.google.accounts.id.renderButton(ref.current, {
        theme: "outline",
        size: "large",
        width: Math.min(320, ref.current.clientWidth),
        locale: i18n.language,
      });
    };
    setError(false);
    if (window.google) render();
    else {
      const script = document.createElement("script");
      script.src = "https://accounts.google.com/gsi/client";
      script.async = true;
      script.onload = render;
      script.onerror = () => {
        if (current) setError(true);
      };
      document.head.append(script);
      return () => {
        current = false;
        script.remove();
      };
    }
    return () => {
      current = false;
    };
  }, [clientId, attempt, i18n.language]);
  return (
    <div aria-busy={busy}>
      <div ref={ref} className="google-button" />
      {busy && <p role="status">{t("loading")}</p>}
      {error && (
        <div role="alert">
          <p>{t("googleFailed")}</p>
          <button onClick={() => setAttempt((v) => v + 1)}>{t("retry")}</button>
        </div>
      )}
    </div>
  );
}
