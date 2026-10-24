import { Component, Suspense, lazy, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import { Auth } from "./auth";
import { NoticeProvider } from "./ui";
import i18n from "./i18n";
import "@fontsource/inter/latin-400.css";
import "@fontsource/inter/latin-500.css";
import "@fontsource/inter/latin-600.css";
import "katex/dist/katex.min.css";
import "./styles.css";

const App = lazy(() =>
  __WEB_ROLE__ === "parent" ? import("./parent") : import("./student"),
);
const updateLanguage = () => {
  document.title = `AI StudyNest · ${i18n.t(__WEB_ROLE__ === "parent" ? "guardian" : "student")}`;
  document.documentElement.lang = i18n.language;
};
updateLanguage();
i18n.on("languageChanged", updateLanguage);
const updateViewport = () =>
  document.documentElement.style.setProperty(
    "--app-height",
    `${window.visualViewport?.height || window.innerHeight}px`,
  );
updateViewport();
window.visualViewport?.addEventListener("resize", updateViewport);
window.addEventListener("resize", updateViewport);
class ErrorBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <main className="loading-page">
        <h1>{i18n.t("error")}</h1>
        <button onClick={() => location.reload()}>{i18n.t("retry")}</button>
      </main>
    ) : (
      this.props.children
    );
  }
}
createRoot(document.getElementById("root")!).render(
  <ErrorBoundary>
    <NoticeProvider>
      <BrowserRouter>
        <Auth>
          {(session, refresh) => (
            <Suspense
              fallback={<p className="loading-page">{i18n.t("loading")}</p>}
            >
              <App session={session} refresh={refresh} />
            </Suspense>
          )}
        </Auth>
      </BrowserRouter>
    </NoticeProvider>
  </ErrorBoundary>,
);
