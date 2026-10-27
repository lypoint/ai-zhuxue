import {
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
  type ReactElement,
} from "react";
import { useTranslation } from "react-i18next";
import { X, Sprout, Menu } from "lucide-react";
import { api, browser, ROLE, type Session } from "./api";
import { languages, setLanguage, tx } from "./i18n";

const Notices = createContext<(message: string, error?: boolean) => void>(
  () => {},
);
export function NoticeProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [notice, setNotice] = useState<{
    message: string;
    error: boolean;
  } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>(undefined);
  const notify = useCallback((message: string, error = false) => {
    clearTimeout(timer.current);
    setNotice({ message, error });
    timer.current = setTimeout(() => setNotice(null), error ? 12000 : 5000);
  }, []);
  useEffect(() => () => clearTimeout(timer.current), []);
  return (
    <Notices.Provider value={notify}>
      {children}
      {notice && (
        <div
          className={`toast ${notice.error ? "error" : ""}`}
          role={notice.error ? "alert" : "status"}
        >
          {tx(notice.message)}
          <button
            className="icon-button"
            aria-label={t("close")}
            onClick={() => setNotice(null)}
          >
            <X size={18} />
          </button>
        </div>
      )}
    </Notices.Provider>
  );
}
export const useNotify = () => useContext(Notices);
export function useAction() {
  const notify = useNotify();
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const lock = useRef(false);
  const run = async <T,>(
    work: () => Promise<T>,
    success?: string,
  ): Promise<T | undefined> => {
    if (lock.current) return;
    lock.current = true;
    setBusy(true);
    try {
      const value = await work();
      if (success) notify(success);
      return value;
    } catch (error) {
      if (!(error instanceof DOMException && error.name === "AbortError"))
        notify(error instanceof Error ? error.message : t("error"), true);
    } finally {
      lock.current = false;
      setBusy(false);
    }
  };
  return { run, busy };
}
export function useResource<T>(path: string | null) {
  const [state, setState] = useState<{
    data: T | null;
    error: string | null;
    loading: boolean;
  }>({ data: null, error: null, loading: true });
  const [version, setVersion] = useState(0);
  const previousPath = useRef(path);
  const reload = useCallback(() => setVersion((v) => v + 1), []);
  useEffect(() => {
    let current = true;
    const changed = previousPath.current !== path;
    previousPath.current = path;
    setState((state) => ({
      data: changed || !path ? null : state.data,
      error: null,
      loading: !!path,
    }));
    if (path)
      void api<T>(path)
        .then((data) => {
          if (current) setState({ data, error: null, loading: false });
        })
        .catch((error) => {
          if (current)
            setState({
              data: null,
              error: String(error.message),
              loading: false,
            });
        });
    return () => {
      current = false;
    };
  }, [path, version]);
  return { ...state, reload };
}
export function ResourceState({
  loading,
  error,
  retry,
}: {
  loading: boolean;
  error: string | null;
  retry: () => void;
}) {
  const { t } = useTranslation();
  if (loading)
    return (
      <p className="muted" role="status">
        {t("loading")}
      </p>
    );
  if (error)
    return (
      <div className="notice error" role="alert">
        <p>{tx(error)}</p>
        <button onClick={retry}>{t("retry")}</button>
      </div>
    );
  return null;
}
export function Empty({ children }: { children?: ReactNode }) {
  const { t } = useTranslation();
  return <div className="empty">{children || t("empty")}</div>;
}
export function Heading({
  title,
  hint,
  actions,
}: {
  title: string;
  hint?: string;
  actions?: ReactNode;
}) {
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        {hint && <p className="muted">{hint}</p>}
      </div>
      {actions}
    </header>
  );
}
export function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: ReactNode;
  hint?: string;
}) {
  const id = useId();
  const control = isValidElement(children)
    ? cloneElement(
        children as ReactElement<{ id?: string; "aria-describedby"?: string }>,
        { id, "aria-describedby": hint ? id + "-hint" : undefined },
      )
    : children;
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      {control}
      {hint && <small id={id + "-hint"}>{hint}</small>}
    </div>
  );
}
export function LanguagePicker() {
  const { t, i18n } = useTranslation();
  const { run, busy } = useAction();
  return (
    <label className="language-picker">
      <span className="sr-only">{t("language")}</span>
      <select
        aria-label={t("language")}
        value={i18n.resolvedLanguage}
        disabled={busy}
        onChange={(e) => void run(() => setLanguage(e.target.value))}
      >
        {Object.entries(languages).map(([key, name]) => (
          <option value={key} key={key}>
            {name}
          </option>
        ))}
      </select>
    </label>
  );
}
export function Brand() {
  return (
    <div className="brand">
      <Sprout size={23} aria-hidden="true" />
      <strong>AI StudyNest</strong>
    </div>
  );
}
export function MenuButton({ onClick }: { onClick: () => void }) {
  const { t } = useTranslation();
  return (
    <button
      className="icon-button mobile-menu"
      onClick={onClick}
      aria-label={t("menu")}
    >
      <Menu />
    </button>
  );
}
export function Dialog({
  title,
  children,
  onClose,
  dismissable = true,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  dismissable?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const { t } = useTranslation();
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog?.showModal();
    return () => {
      dialog?.close();
      if (previous instanceof HTMLElement && previous.isConnected)
        previous.focus();
    };
  }, []);
  return (
    <dialog
      ref={ref}
      onCancel={(e) => {
        e.preventDefault();
        if (dismissable) onClose();
      }}
      onClick={(e) => {
        if (dismissable && e.target === ref.current) {
          const r = ref.current.getBoundingClientRect();
          if (
            e.clientX < r.left ||
            e.clientX > r.right ||
            e.clientY < r.top ||
            e.clientY > r.bottom
          )
            onClose();
        }
      }}
      aria-labelledby="dialog-heading"
    >
      <div className="dialog-heading">
        <h2 id="dialog-heading">{title}</h2>
        {dismissable && (
          <button
            className="icon-button"
            type="button"
            onClick={onClose}
            aria-label={t("close")}
          >
            <X />
          </button>
        )}
      </div>
      {children}
    </dialog>
  );
}
export function Confirm({
  title,
  hint,
  action,
  onClose,
  typed = false,
}: {
  title: string;
  hint?: string;
  action: () => Promise<void>;
  onClose: () => void;
  typed?: boolean;
}) {
  const { t } = useTranslation();
  const [value, setValue] = useState("");
  const { busy, run } = useAction();
  return (
    <Dialog title={title} onClose={onClose}>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void run(async () => {
            await action();
            onClose();
          });
        }}
      >
        <p>{hint}</p>
        {typed && (
          <Field label={t("confirmDelete")}>
            <input
              autoComplete="off"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              required
              pattern="DELETE"
            />
          </Field>
        )}
        <div className="actions">
          <button type="button" onClick={onClose}>
            {t("cancel")}
          </button>
          <button
            className="danger"
            disabled={busy || (typed && value !== "DELETE")}
          >
            {busy ? t("loading") : t("confirm")}
          </button>
        </div>
      </form>
    </Dialog>
  );
}
export function formData(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
  return Object.fromEntries(
    new FormData(event.currentTarget).entries(),
  ) as Record<string, string>;
}
export function download(data: unknown, filename: string) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }),
  );
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
export async function copy(text: string) {
  if (!navigator.clipboard)
    throw new Error(
      "Clipboard unavailable. Select and copy the code manually.",
    );
  await navigator.clipboard.writeText(text);
}
export function Legal({
  page: initialPage,
  onClose,
}: {
  page: string;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [page, setPage] = useState(initialPage);
  useEffect(() => setPage(initialPage), [initialPage]);
  const contactEmail = "support@aistudynest.com";
  return (
    <Dialog title={t(page)} onClose={onClose}>
      <p className="prose">{t(page + "Body")}</p>
      {(page === "privacy" || page === "terms") && <p className="prose">
        <a href="https://aistudynest.com/pricing/#models" target="_blank" rel="noopener noreferrer">{t("teachers")} ↗</a>
      </p>}
      {__WEB_ROLE__ === "parent" && page === "privacy" && <p className="prose">
        {tx("允许 Firebase Analytics 收集家长网站的使用事件和浏览器标识，用于分析注册与订阅转化；不上传孩子信息或学习内容。可随时关闭。")}
      </p>}
      <p>
        {t("contactUs")}: <a href={`mailto:${contactEmail}`}>{contactEmail}</a>
      </p>
      <nav className="actions">
        <button className="text-button" onClick={() => setPage("privacy")} aria-current={page === "privacy" ? "page" : undefined}>{t("privacy")}</button>
        <button className="text-button" onClick={() => setPage("terms")} aria-current={page === "terms" ? "page" : undefined}>{t("terms")}</button>
      </nav>
      {(page === "privacy" || page === "terms") && <p>
        <a href={`https://aistudynest.com/${page}/`} target="_blank" rel="noopener noreferrer">{t(page)} ↗</a>
      </p>}
      <p className="muted">{t("visibility")}</p>
    </Dialog>
  );
}
export function AccountSettings({
  session,
  refresh,
}: {
  session: Session;
  refresh: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const { busy, run } = useAction();
  const [confirm, setConfirm] = useState<string | null>(null);
  const [legal, setLegal] = useState<string | null>(null);
  const logout = async (all = false) => {
    await browser(all ? "/logout-all" : "/logout", "POST");
    clearPrivateStorage();
    window.dispatchEvent(new Event("session-expired"));
  };
  return (
    <>
      <Heading title={t("settings")} />
      <section className="panel">
        <h2>{t("profile")}</h2>
        <p>{session.nickname}</p>
        <LanguagePicker />
        {ROLE === "parent" && (
          <form
            onSubmit={(event) => {
              const data = formData(event);
              void run(async () => {
                await api("/parent/guardian/nickname", "PUT", data);
                await refresh();
              }, t("changed"));
            }}
          >
            <Field label={t("name")}>
              <input
                name="nickname"
                defaultValue={session.nickname}
                required
                maxLength={50}
              />
            </Field>
            <button className="primary" disabled={busy}>
              {t("save")}
            </button>
          </form>
        )}
      </section>
      <section className="panel">
        <h2>{t("danger")}</h2>
        <div className="actions">
          <button onClick={() => setLegal("privacy")}>{t("privacy")}</button>
          <button onClick={() => setLegal("help")}>{t("help")}</button>
          <button onClick={() => setLegal("terms")}>{t("terms")}</button>
        </div>
        <div className="stack">
          <button onClick={() => void run(() => logout())} disabled={busy}>
            {t("signOut")}
          </button>
          <button onClick={() => setConfirm("all")}>{t("signOutAll")}</button>
          <button className="danger" onClick={() => setConfirm("delete")}>
            {t(ROLE === "parent" ? "deleteFamily" : "deleteAccount")}
          </button>
        </div>
      </section>
      {legal && <Legal page={legal} onClose={() => setLegal(null)} />}
      {confirm && (
        <Confirm
          title={t(confirm === "all" ? "signOutAll" : "deleteAccount")}
          hint={t(confirm === "all" ? "signOutAllHint" : "deleteHint")}
          typed={confirm === "delete"}
          onClose={() => setConfirm(null)}
          action={async () => {
            if (confirm === "all") await logout(true);
            else {
              await api(
                ROLE === "parent"
                  ? "/parent/account/deletion-request"
                  : "/auth/student/account/delete",
                "POST",
                { confirmation: "DELETE" },
              );
              clearPrivateStorage();
              window.dispatchEvent(new Event("session-expired"));
            }
          }}
        />
      )}
    </>
  );
}
export function clearPrivateStorage() {
  try {
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith("ai-learning-"))
      .forEach((key) => sessionStorage.removeItem(key));
  } catch {
    /* No storage available. */
  }
}

export function useNarrowNav() {
  const [narrow, setNarrow] = useState(
    () => matchMedia("(max-width:1050px)").matches,
  );
  useEffect(() => {
    const media = matchMedia("(max-width:1050px)");
    const change = () => setNarrow(media.matches);
    media.addEventListener("change", change);
    return () => media.removeEventListener("change", change);
  }, []);
  return narrow;
}
