import { initializeApp } from "firebase/app";
import { initializeAnalytics, isSupported, logEvent, setAnalyticsCollectionEnabled, setConsent } from "firebase/analytics";

export async function createAnalytics(config: NonNullable<typeof __PARENT_FIREBASE_CONFIG__>, allowed: () => boolean) {
  if (!await isSupported() || !allowed()) return null;
  const consent = (granted: boolean) => setConsent({
    analytics_storage: granted ? "granted" : "denied", ad_storage: "denied",
    ad_user_data: "denied", ad_personalization: "denied",
  });
  consent(true);
  const analytics = initializeAnalytics(initializeApp(config, "parent-web"), { config: {
    send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false,
    debug_mode: import.meta.env.DEV,
    page_location: `${location.origin}/`, page_title: "AI StudyNest Parent", page_referrer: "",
  } });
  return {
    log: (event: string, parameters: Record<string, string | number>) => logEvent(analytics, event, parameters),
    consent: (granted: boolean) => { setAnalyticsCollectionEnabled(analytics, granted); consent(granted); },
  };
}
