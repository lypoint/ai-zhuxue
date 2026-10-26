import { useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { analyticsConfigured, analyticsConsent, analyticsPage, setAnalyticsConsent, track } from "./parent-analytics";
import { Dialog, Legal } from "./ui";
import { tx } from "./i18n";

export default function AnalyticsConsent() {
  const { t } = useTranslation();
  const [consent, update] = useState(analyticsConsent);
  const [open, setOpen] = useState(consent === null);
  const [legal, setLegal] = useState(false);
  const { pathname } = useLocation();
  const page = analyticsPage(pathname);
  useEffect(() => {
    const change = () => update(analyticsConsent());
    window.addEventListener("parent-analytics-consent", change);
    return () => window.removeEventListener("parent-analytics-consent", change);
  }, []);
  useEffect(() => { if (consent === true) void track("page_view", {}, page); }, [consent, page]);
  if (!analyticsConfigured) return null;
  const choose = (value: boolean) => { setAnalyticsConsent(value); setOpen(false); };
  return <>
    <button className="text-button analytics-preferences" onClick={() => setOpen(true)}>{tx("Data Privacy & Consent")}</button>
    {open && <Dialog title={tx("Data Privacy & Consent")} onClose={() => setOpen(false)}>
      <p>{tx("允许 Firebase Analytics 收集家长网站的使用事件和浏览器标识，用于分析注册与订阅转化；不上传孩子信息或学习内容。可随时关闭。")}</p>
      <div className="actions">
        <button onClick={() => choose(false)}>{tx("Essential Only")}</button>
        <button className="primary" onClick={() => choose(true)}>{tx("Accept All")}</button>
        <button className="text-button" onClick={() => setLegal(true)}>{t("privacy")}</button>
        <a href="https://firebase.google.com/support/privacy" target="_blank" rel="noopener noreferrer">Firebase Privacy</a>
      </div>
    </Dialog>}
    {legal && <Legal page="privacy" onClose={() => setLegal(false)} />}
  </>;
}
