import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import catalogs from "../../app/app_core/assets/i18n/catalog.json";
import webTranslations from "./web-translations.json";

export const languages = {
  en: "English",
  "zh-Hans": "简体中文",
  "zh-Hant": "繁體中文",
  ja: "日本語",
  ko: "한국어",
  de: "Deutsch",
  es: "Español",
};
const en: Record<string, string> = {
  confirmFamilyZone:
    "Ask your parent to confirm the family time zone before connecting.",
  imageReviewFailed: "The image did not pass review. Please choose another.",
  imageServiceUnavailable:
    "Image storage or review is unavailable. Please retry.",
  verificationFailed:
    "Your request could not be verified. Refresh and try again.",
  invalidTimezone: "Choose a valid time zone.",
  incompleteAnswer: "The answer could not be completed. Please retry.",
  cropError: "Could not crop the image. Please try again.",
  clipboardError: "Clipboard unavailable. Select and copy the code manually.",
  formError: "Please check the form and try again.",
  invalidScore: "Score cannot exceed the maximum",
  webBrowser: "Web browser",
  rotatePhoto: "Rotate clockwise",
  backToLatest: "Back to latest messages",
  suggestions: "Suggestions",
  guardian: "Parent",
  gradeDeleted: "Deleted",
  restored: "Restored",
  welcomeNotification: "Welcome to AI StudyNest",
  safetyNotification: "Safety-related content was blocked",
  offTopicNotification: "A question outside learning was blocked",
  trialNotification:
    "Your 30-day free trial has started. Create a connection code to connect your child's learning device.",
  you: "You",
  student: "Student",
  menu: "Open navigation",
  skipContent: "Skip to content",
  basedOnRecords: "Based on recorded learning activity",
  freeTrial: "Free trial",
  not_needed: "No action needed",
  pending: "Pending",
  open: "Open",
  resolved: "Reviewed",
  closed: "Closed",
  school_stress: "School stress",
  peer_support: "Peer support",
  low_mood: "Low mood",
  self_harm: "Expressions about self-harm",
  urgent: "Needs immediate attention",
  observe: "Observe and talk together",
  attention: "Needs attention",
  study: "Learning",
  entertainment: "Entertainment",
  sensitive: "Safety-related",
  allow: "Allowed",
  reject: "Blocked",
  rewrite: "Guided back to learning",
  app: "AI StudyNest",
  parentSpace: "Parent space",
  studentSpace: "Student space",
  overview: "Overview",
  children: "Children & devices",
  activity: "Learning activity",
  schedule: "Learning schedule",
  subscription: "Subscription",
  settings: "Settings",
  notifications: "Notifications",
  grades: "Grades & growth",
  learning: "Learning & rewards",
  favorites: "Saved moments",
  reports: "My reports",
  assessments: "Assessments",
  welcome: "A little progress, every day.",
  overviewHint: "A window into your child's learning. A little room to grow.",
  newChat: "New conversation",
  ask: "Ask a question, or add a photo…",
  send: "Send",
  stop: "Stop generating",
  retry: "Retry",
  loading: "Loading…",
  saved: "Saved",
  save: "Save changes",
  cancel: "Cancel",
  close: "Close",
  back: "Back",
  next: "Next",
  search: "Search",
  searchHint: "Search conversations",
  noResults: "No results",
  empty: "Nothing here yet.",
  edit: "Edit",
  remove: "Delete",
  restore: "Restore",
  history: "Version history",
  conversationHistory: "Conversations",
  name: "Name",
  nickname: "Nickname",
  ageBand: "Age range",
  addChild: "Add a child",
  connectDevice: "Connect a device",
  disconnect: "Disconnect device",
  currentDevice: "Current device",
  noDevice: "No device connected",
  copy: "Copy",
  copied: "Copied",
  newCode: "Generate a new code",
  connect: "Connect to my family",
  code: "Connection code",
  codeHint: "Enter 8-character code",
  connectHeading: "Your next question starts here.",
  connectHint:
    "Ask your parent for the connection code from their Parent space.",
  codeHelp:
    "Your parent creates the code; you enter it here. No Google account is needed.",
  expiredCode:
    "Codes expire after 10 minutes. Ask your parent for a new one if needed.",
  validUntil: "Valid until",
  replaceWarning:
    "One learning device at a time. Connecting this browser signs the child out of their current learning device. Learning history is kept.",
  createFamily: "Make room for curiosity.",
  setupHint:
    "Create a child profile, confirm your family time zone, then connect a learning device.",
  familyTimezone: "Family time zone",
  timezoneHint:
    "Learning days, daily limits and quiet hours follow this time zone, including daylight-saving changes.",
  timezoneRate:
    "Time zone changes are limited to once every 24 hours. Existing usage is retained.",
  chooseChild: "Choose a child",
  noChildren: "Add your first child to get started.",
  learningTime: "Learning time today",
  questions: "Questions",
  thisWeek: "This week",
  minutes: "minutes",
  activeDays: "Active days",
  today: "Today",
  remaining: "{{count}} min left",
  unlimited: "No time limit",
  recent: "Recent conversations",
  viewAll: "View all learning activity",
  visibility: "Your parent can read your conversations. AI can make mistakes.",
  parentVisibility:
    "You can read your child's full learning conversations, including conversations they removed from their own history.",
  beforeBegin: "Before your first question",
  understand: "I understand. Start learning",
  privacy: "Privacy",
  help: "Help",
  contactUs: "Contact us",
  terms: "Terms",
  googleHint:
    "Sign in with the same Google account you use for the Google Play parent app.",
  googleUnavailable: "Google sign-in is not configured for this environment.",
  signIn: "Sign in to your family",
  googleFailed:
    "Google sign-in could not load. Check your connection and retry.",
  signOut: "Sign out of this browser",
  signOutAll: "Sign out of all devices",
  signOutAllHint: "This signs this account out on Web and in the native app.",
  deleteAccount: "Delete account",
  deleteFamily: "Request family account deletion",
  deleteHint:
    "Type DELETE to confirm. This action disables access and starts the account deletion process. Subscription cancellation must be handled in the original purchase channel.",
  confirm: "Confirm",
  confirmDelete: "Type DELETE",
  danger: "Account & privacy",
  language: "Language",
  profile: "Profile",
  changed: "Changes saved.",
  error: "Something went wrong. Please retry.",
  sessionExpired: "Your session has expired. Please sign in again.",
  offline: "You are offline. Your draft is kept on this device.",
  online: "Connection restored.",
  noPayment: "Website subscriptions and payments are not available yet.",
  access: "Learning access",
  purchaseSource: "Purchase source",
  managePlay: "Manage on Google Play",
  active: "Active",
  inactive: "Inactive",
  expires: "Expires",
  seats: "Child profiles available",
  timeUsed: "Time used",
  dailyMinutes: "Daily learning time (minutes)",
  dailyMessages: "Daily question limit",
  quiet: "Quiet hours",
  enabled: "Enabled",
  startHour: "Start hour",
  endHour: "End hour",
  noLimitHint: "0–480 minutes; 0 means no limit.",
  equalHours: "Equal start and end hours mean no quiet period.",
  fence: "Learning boundaries",
  fenceLevel: "Boundary level",
  strict: "Strict",
  relaxed: "Relaxed",
  off: "Off",
  forbidden: "Custom blocked words",
  forbiddenHint:
    "One phrase per line. These are shared with your native app settings.",
  notifyFence: "Learning boundary notifications",
  notifyHint: "Security alerts always remain enabled.",
  rename: "Rename",
  pin: "Pin",
  unpin: "Unpin",
  deleteChat:
    "Remove this conversation from your history? Your parent can still review it.",
  teacher: "Learning guide",
  teachers: "Choose a teacher",
  teacherLocked: "This teacher is currently unavailable for your family.",
  noTeachers:
    "No teacher is currently available. Please ask your parent or try again later.",
  newTeacherHint:
    "A different teacher starts a new conversation. Existing conversations keep their original teacher.",
  addPhoto: "Add photo",
  camera: "Take photo",
  crop: "Crop image",
  cropHint:
    "Adjust the crop, then add the photo. Images are compressed and metadata is removed.",
  applyCrop: "Use this photo",
  uploadFailed: "Photo upload failed. Retry or remove the photo.",
  uploading: "Uploading photo…",
  imageLimit: "You can attach up to 3 images.",
  imageType: "Choose a JPEG, PNG or WebP image.",
  viewImage: "View image",
  imageUnavailable: "Image unavailable",
  diagram: "Add an illustration",
  pendingImage: "Preparing illustration…",
  feedback: "Did this help?",
  understood: "I understand",
  not_understood: "I don't understand yet",
  continue: "Keep explaining",
  report: "Report this answer",
  reason: "Reason",
  submit: "Submit",
  removeSaved: "Remove saved moment",
  source: "View source conversation",
  sourceUnavailable: "The original conversation is no longer in your history.",
  boundaries: "Boundary events",
  all: "All",
  deleted: "Removed by student",
  unreadOnly: "Unread only",
  readAll: "Mark all as read",
  read: "Read",
  unread: "Unread",
  details: "View details",
  previous: "Previous",
  more: "Next page",
  export: "Export learning data",
  feedbackNote: "Tell us what needs another look",
  flagged: "Flag for review",
  takeBreak: "Time for a short break",
  breakHint:
    "Stretch, look away from the screen, or tell someone about the idea you explored.",
  quietPeriod: "Quiet time: {{start}}–{{end}}",
  timeUp: "Your learning time for today is used up.",
  draftSaved: "Your draft and conversation are saved.",
  checkAgain: "Check availability",
  subject: "Subject",
  title: "Title",
  score: "Score",
  maxScore: "Maximum score",
  examDate: "Date",
  term: "Term",
  gradeType: "Type",
  note: "Notes",
  exam: "Exam",
  homework: "Homework",
  quiz: "Quiz",
  other: "Other",
  addGrade: "Add grade",
  trend: "Grade trend",
  trendHint:
    "Choose one subject to compare grades fairly. Scores are shown with their original maximum.",
  version: "Version",
  from: "From",
  to: "To",
  generate: "Generate assessment",
  academic: "Learning assessment",
  wellbeing: "Wellbeing observations",
  assessmentHint:
    "These are explainable estimates based on available learning records, not school grades or a diagnosis.",
  evidence: "Evidence",
  acknowledge: "Acknowledge",
  notNeeded: "No action needed",
  acknowledged: "Acknowledged",
  balance: "Available stars",
  earned: "Earned",
  spent: "Redeemed",
  rewardRule:
    "One participation star per day after a completed learning exchange and any learning feedback. Changing feedback does not award extra stars.",
  agreements: "Family reward agreements",
  reward: "Reward",
  stars: "Stars required",
  fulfillment: "How and when to fulfill",
  propose: "Propose reward",
  accept: "Accept agreement",
  redeem: "Redeem",
  fulfilled: "Fulfilled",
  fulfill: "Mark fulfilled",
  awaiting: "Waiting for acceptance",
  redemptions: "Redemptions",
  feedbackHistory: "Learning feedback",
  bookmark: "Save moment",
  connected: "Device connected.",
  nameHint: "Use a nickname, not personal contact details.",
  deviceName: "Learning device name",
  releaseChild:
    "Remove this child profile and disconnect its learning devices?",
  dataKept:
    "Learning records are retained for family review unless a full deletion is requested.",
  modelUsage: "AI usage",
  tokensIn: "Input tokens",
  tokensOut: "Output tokens",
  showDeleted: "Include removed items",
  newConversation: "What would you like to understand today?",
  topicHint: "Start with a question. We can work through it together.",
  deletedMessage: "This conversation was removed from the student history.",
  invalidCode:
    "This connection code is invalid, expired, or has already been used.",
  fileTooLarge: "This image is too large. Choose a smaller image.",
  deleteGrade: "Delete this grade? It can be restored from removed items.",
  unknownError:
    "The request could not be completed. Please retry or contact support.",
  privacyBody:
    "Your family can review learning conversations. Necessary messages and reviewed images are processed by the configured AI providers. Avoid sharing contact details or other unnecessary personal information. Account deletion is available in Settings.",
  helpBody:
    "Your parent creates connection codes and manages learning time. You can ask questions, add photos, save ideas and give feedback. Website restrictions and device lock settings must be configured by your parent in the device settings.",
  termsBody:
    "AI StudyNest supports learning and does not replace teachers or professional advice. AI answers and observations can be inaccurate. A guardian should supervise use. Website payments are not offered in this version.",
  reconnect: "Reconnect",
  networkError:
    "Network unavailable. Please check the latest state before retrying.",
  loadingAnswer: "Thinking it through…",
  stopped: "Generation stopped. You can retry the saved question.",
  inputHint: "Enter to send · Shift + Enter for a new line",
  cropLeft: "Crop from left (%)",
  cropTop: "Crop from top (%)",
  cropWidth: "Crop width (%)",
  cropHeight: "Crop height (%)",
};
const catalog = catalogs as unknown as Record<string, Record<string, string>>;
const byEnglish = new Map(
  Object.entries(catalog.en).map(([source, value]) => [
    value.trim().toLowerCase(),
    source,
  ]),
);
const resources: Record<string, { translation: Record<string, string> }> = {};
for (const locale of Object.keys(languages)) {
  const translation: Record<string, string> = {};
  for (const [key, value] of Object.entries(en)) {
    const source = byEnglish.get(value.toLowerCase());
    translation[key] =
      locale === "en" ? value : (source && catalog[locale]?.[source]) || value;
  }
  resources[locale] = { translation };
}
const core: Record<string, string[]> = {
  overview: ["概览", "概覽", "概要", "개요", "Übersicht", "Resumen"],
  children: [
    "孩子与设备",
    "孩子與裝置",
    "子どもと端末",
    "자녀 및 기기",
    "Kinder & Geräte",
    "Hijos y dispositivos",
  ],
  activity: [
    "学习记录",
    "學習紀錄",
    "学習記録",
    "학습 기록",
    "Lernaktivität",
    "Actividad de aprendizaje",
  ],
  schedule: [
    "学习计划",
    "學習計畫",
    "学習スケジュール",
    "학습 일정",
    "Lernzeiten",
    "Horario de aprendizaje",
  ],
  favorites: [
    "收藏",
    "收藏",
    "保存した内容",
    "저장한 내용",
    "Gespeicherte Momente",
    "Momentos guardados",
  ],
  parentSpace: [
    "家长空间",
    "家長空間",
    "保護者スペース",
    "보호자 공간",
    "Elternbereich",
    "Espacio para padres",
  ],
  studentSpace: [
    "学生空间",
    "學生空間",
    "学習スペース",
    "학생 공간",
    "Lernbereich",
    "Espacio del estudiante",
  ],
  welcome: [
    "每天，多懂一点。",
    "每天，多懂一點。",
    "毎日、少しずつ前へ。",
    "매일 조금씩 성장해요.",
    "Jeden Tag ein kleiner Fortschritt.",
    "Un pequeño progreso cada día.",
  ],
  connectDevice: [
    "连接学习设备",
    "連接學習裝置",
    "学習端末を接続",
    "학습 기기 연결",
    "Lerngerät verbinden",
    "Conectar un dispositivo",
  ],
  connect: [
    "连接我的家庭",
    "連接我的家庭",
    "家族に接続",
    "가족에 연결",
    "Mit meiner Familie verbinden",
    "Conectar con mi familia",
  ],
  code: [
    "连接码",
    "連接碼",
    "接続コード",
    "연결 코드",
    "Verbindungscode",
    "Código de conexión",
  ],
  signOut: [
    "退出当前浏览器",
    "登出目前瀏覽器",
    "このブラウザからログアウト",
    "이 브라우저에서 로그아웃",
    "In diesem Browser abmelden",
    "Cerrar sesión en este navegador",
  ],
  noPayment: [
    "网站订阅与支付暂未开放。",
    "網站訂閱與付款暫未開放。",
    "Webの購読・支払いは未提供です。",
    "웹 구독 및 결제는 아직 제공되지 않습니다.",
    "Web-Abonnements und Zahlungen sind noch nicht verfügbar.",
    "Las suscripciones y los pagos web aún no están disponibles.",
  ],
  visibility: [
    "家长可以查看你的对话。AI 可能出错。",
    "家長可以查看你的對話。AI 可能出錯。",
    "保護者は会話を確認できます。AIは間違えることがあります。",
    "보호자는 대화를 볼 수 있습니다. AI는 실수할 수 있습니다.",
    "Deine Eltern können deine Gespräche lesen. KI kann Fehler machen.",
    "Tus padres pueden leer tus conversaciones. La IA puede equivocarse.",
  ],
};
for (const [key, values] of Object.entries(core))
  ["zh-Hans", "zh-Hant", "ja", "ko", "de", "es"].forEach((locale, index) => {
    resources[locale].translation[key] = values[index];
  });
for (const [key, values] of Object.entries(webTranslations))
  ["zh-Hans", "zh-Hant", "ja", "ko", "de", "es"].forEach((locale, index) => {
    resources[locale].translation[key] = values[index];
  });
function resolve(value: string) {
  if (/^zh/i.test(value))
    return /Hant|TW|HK|MO/i.test(value) ? "zh-Hant" : "zh-Hans";
  return (
    Object.keys(languages).find((locale) =>
      value.toLowerCase().startsWith(locale),
    ) || "en"
  );
}
let saved: string | null = null;
try {
  saved = localStorage.getItem("ai-learning-language");
} catch {
  /* Browser privacy mode can disable storage. */
}
void i18n.use(initReactI18next).init({
  resources,
  lng: resolve(saved || navigator.language),
  fallbackLng: "en",
  keySeparator: false,
  interpolation: { escapeValue: false },
});
export function setLanguage(value: string) {
  try {
    localStorage.setItem("ai-learning-language", value);
  } catch {
    /* Language still changes for this page. */
  }
  void i18n.changeLanguage(value);
}
export function tx(source: string): string {
  const locale = i18n.resolvedLanguage || "en";
  const systemMessages: Record<string, string> = {
    "The image is too large.": "fileTooLarge",
    "Choose a valid IANA time zone.": "invalidTimezone",
    "The family time zone can be changed once every 24 hours.": "timezoneRate",
    "The image could not be loaded. Please retry.": "imageUnavailable",
    "The connection ended before the answer finished. Please retry.":
      "incompleteAnswer",
    "Streaming is unavailable. Please retry.": "incompleteAnswer",
    "Origin is not allowed.": "verificationFailed",
    "Cross-site access is not allowed.": "verificationFailed",
    "A trusted Origin is required.": "verificationFailed",
    "Web access is unavailable.": "unknownError",
    "This Web space is not served on this host.": "unknownError",
    "Web origins must be configured independently with HTTPS.": "unknownError",
    "This API is unavailable in this Web space.": "unknownError",
    "欢迎使用 AI 助学": "welcomeNotification",
    "⚠️ 已拦截一条敏感内容": "safetyNotification",
    已拦截一条非学习内容: "offTopicNotification",
    "已为您开启 30 天免费试用。请生成绑定码激活孩子端，开启受保护的学习之旅。":
      "trialNotification",
  };
  if (systemMessages[source]) return i18n.t(systemMessages[source]);
  const uiKey = Object.keys(en).find((key) => en[key] === source);
  if (uiKey) return i18n.t(uiKey);
  if (catalog[locale]?.[source]) return catalog[locale][source];
  for (const template of catalogs._messages) {
    if (!template.includes("{")) continue;
    const pattern = template
      .split(/(\{\d+\})/)
      .map((part) =>
        /^\{\d+\}$/.test(part)
          ? "(.*?)"
          : part.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
      )
      .join("");
    const match = source.match(new RegExp("^" + pattern + "$", "s"));
    if (match)
      return (catalog[locale]?.[template] || template).replace(
        /\{(\d+)\}/g,
        (_, index: string) => match[Number(index) + 1] || "",
      );
  }
  if (source.includes("bind code")) return i18n.t("invalidCode");
  if (/[\u3400-\u9fff]/.test(source)) return i18n.t("unknownError");
  return source;
}

export function contentText(source: string): string {
  const translated = tx(source);
  return translated === i18n.t("unknownError") ? source : translated;
}
export function date(
  value: string | null | undefined,
  timezone?: string | null,
  dayOnly = false,
) {
  if (!value) return "—";
  if (/^\d{4}-\d{2}-\d{2}$/.test(value))
    return new Intl.DateTimeFormat(i18n.language, {
      dateStyle: "medium",
      timeZone: "UTC",
    }).format(new Date(value + "T12:00:00Z"));
  const stamp = /Z$|[+-]\d{2}:\d{2}$/.test(value) ? value : value + "Z";
  return new Intl.DateTimeFormat(i18n.language, {
    dateStyle: "medium",
    ...(dayOnly ? {} : { timeStyle: "short" }),
    ...(timezone ? { timeZone: timezone } : {}),
  }).format(new Date(stamp));
}
export function number(value: number) {
  return new Intl.NumberFormat(i18n.language, {
    maximumFractionDigits: 2,
  }).format(value);
}
export default i18n;
