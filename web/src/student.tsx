import { observeImagePerformance } from "./request-performance";
import { enableStudentAnalytics, trackStudent } from "./student-analytics";
import { useEffect, useRef, useState } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowUp,
  Bookmark,
  GraduationCap,
  Settings,
  Sparkles,
  MessagesSquare,
  BarChart3,
  Flag,
  ImagePlus,
  Square,
  ChevronDown,
  Clock3,
} from "lucide-react";
import {
  api,
  sendPerformance,
  browser,
  request,
  stream,
  type Conversation,
  type ImageJob,
  type Message,
  type Session,
  type Stats,
  type Favorite,
  type ImageBlock,
} from "./api";
import {
  AccountSettings,
  Brand,
  Confirm,
  Dialog,
  Empty,
  Field,
  formData,
  Heading,
  LanguagePicker,
  MenuButton,
  useNarrowNav,
  ResourceState,
  useAction,
  useNotify,
  useResource,
} from "./ui";
import { date, number, tx, contentText } from "./i18n";
import { Favorites, MessageCard } from "./content";
import { TeacherAvatar } from "./teacher-avatar";
import { PhotoPicker, type Attachment } from "./photo";
import Grades from "./grades";
import Learning from "./learning";
import Assessments from "./assessments";

type Availability = {
  resting: boolean;
  remaining_seconds: number | null;
  used_seconds: number;
  daily_minutes_cap: number;
  quiet_start: number;
  quiet_end: number;
  timezone: string | null;
  refresh_after_seconds: number;
  day: string;
};
type Teacher = {
  teacher_id: number | null;
  name: string;
  avatar_url?: string;
  selected: boolean;
  access: string;
  capabilities?: {
    image_input: boolean;
    image_output: boolean;
    reason: string;
  };
};
export default function Student({
  session,
  refresh,
}: {
  session: Session;
  refresh: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const location = useLocation();
  const navigate = useNavigate();
  const [menu, setMenu] = useState(false);
  const narrow = useNarrowNav();
  const [availability, setAvailability] = useState<Availability | null>(null);
  useEffect(() => observeImagePerformance(sendPerformance), []);
  useEffect(() => {
    enableStudentAnalytics(true);
    trackStudent("student_page_view", location.pathname);
    return () => enableStudentAnalytics(false);
  }, [location.pathname]);
  const [online, setOnline] = useState(navigator.onLine);
  const [guide, setGuide] = useState(() => {
    try {
      return !sessionStorage.getItem(`ai-learning-guide-${session.id}`);
    } catch {
      return true;
    }
  });
  const refreshAvailability = async () => {
    setAvailability(await api<Availability>("/chat/availability"));
  };
  useEffect(() => {
    let current = true;
    const poll = () => {
      if (!document.hidden)
        void api<Availability>("/chat/availability")
          .then((data) => {
            if (current) setAvailability(data);
          })
          .catch(() => {});
    };
    poll();
    const timer = setInterval(poll, 15000);
    const connected = () => {
      setOnline(navigator.onLine);
      if (navigator.onLine) poll();
    };
    window.addEventListener("online", connected);
    window.addEventListener("offline", connected);
    document.addEventListener("visibilitychange", poll);
    return () => {
      current = false;
      clearInterval(timer);
      window.removeEventListener("online", connected);
      window.removeEventListener("offline", connected);
      document.removeEventListener("visibilitychange", poll);
    };
  }, []);
  useEffect(() => {
    if (
      location.pathname !== "/chat" ||
      guide ||
      !availability ||
      availability.resting ||
      availability.remaining_seconds === 0
    )
      return;
    let visibleSince = performance.now();
    let active = !document.hidden;
    const post = (seconds: number) => {
      void request("/heartbeat", {
        method: "POST",
        body: JSON.stringify({ seconds }),
        keepalive: true,
      })
        .then(() => refreshAvailability())
        .catch(() => {});
    };
    const flush = () => {
      if (!active) return;
      const seconds = Math.min(
        90,
        Math.floor((performance.now() - visibleSince) / 1000),
      );
      visibleSince = performance.now();
      post(seconds);
    };
    const change = () => {
      if (document.hidden) {
        flush();
        active = false;
      } else {
        active = true;
        visibleSince = performance.now();
        post(0);
      }
    };
    post(0);
    const timer = setInterval(flush, 15000);
    document.addEventListener("visibilitychange", change);
    window.addEventListener("pagehide", flush);
    return () => {
      flush();
      clearInterval(timer);
      document.removeEventListener("visibilitychange", change);
      window.removeEventListener("pagehide", flush);
    };
  }, [
    location.pathname,
    guide,
    availability?.resting,
    availability?.remaining_seconds === 0,
  ]);
  const nav = [
    ["/chat", "studentSpace", MessagesSquare],
    ["/favorites", "favorites", Bookmark],
    ["/learning", "learning", Sparkles],
    ["/grades", "grades", GraduationCap],
    ["/assessments", "assessments", BarChart3],
    ["/stats", "activity", BarChart3],
    ["/reports", "reports", Flag],
    ["/settings", "settings", Settings],
  ] as const;
  const source = (conversation: number, message?: number | null) =>
    navigate(
      `/chat?conversation=${conversation}${message ? "&message=" + message : ""}`,
    );
  return (
    <div
      className={`app-shell student-shell ${location.pathname === "/chat" ? "chat-mode" : ""}`}
    >
      <a className="skip-link" href="#main-content">
        {t("skipContent")}
      </a>
      {menu && (
        <button
          className="sidebar-scrim"
          aria-label={t("close")}
          onClick={() => setMenu(false)}
        />
      )}
      <aside
        className={`sidebar ${menu ? "open" : ""}`}
        inert={narrow && !menu}
        aria-hidden={narrow && !menu}
      >
        <Brand />
        <span className="eyebrow">{t("studentSpace")}</span>
        <nav aria-label={t("studentSpace")}>
          {nav.map(([path, key, Icon]) => (
            <NavLink key={path} to={path} onClick={() => setMenu(false)}>
              <Icon size={19} />
              {t(key)}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-profile">{session.nickname}</div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <MenuButton onClick={() => setMenu((v) => !v)} />
          <small>{session.nickname}</small>
          <div className="topbar-end">
            {availability && (
              <span className="time-badge">
                <Clock3 size={16} />
                {availability.remaining_seconds === null
                  ? t("unlimited")
                  : t("remaining", {
                      count: Math.ceil(availability.remaining_seconds / 60),
                    })}
              </span>
            )}
            <LanguagePicker />
          </div>
        </header>
        {!online && (
          <p className="offline-banner" role="status">
            {t("offline")}
          </p>
        )}
        <main
          id="main-content"
          className={`page-content ${location.pathname === "/chat" ? "chat-content" : ""}`}
        >
          <Routes>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route
              path="/chat"
              element={
                <Chat
                  session={session}
                  availability={availability}
                  refreshAvailability={refreshAvailability}
                  online={online}
                />
              }
            />
            <Route
              path="/favorites"
              element={
                <>
                  <Heading title={t("favorites")} />
                  <Favorites path="/chat/favorites" onSource={source} />
                </>
              }
            />
            <Route
              path="/learning"
              element={
                <>
                  <Heading title={t("learning")} />
                  <Learning prefix="/chat" />
                </>
              }
            />
            <Route
              path="/grades"
              element={
                <>
                  <Heading title={t("grades")} />
                  <Grades prefix="/chat" timezone={session.timezone} />
                </>
              }
            />
            <Route
              path="/assessments"
              element={
                <>
                  <Heading title={t("assessments")} />
                  <Assessments
                    prefix="/chat"
                    timezone={session.timezone}
                    onSource={source}
                  />
                </>
              }
            />
            <Route path="/stats" element={<StudentStats />} />
            <Route
              path="/reports"
              element={<Reports source={source} timezone={session.timezone} />}
            />
            <Route
              path="/settings"
              element={<AccountSettings session={session} refresh={refresh} />}
            />
            <Route path="*" element={<Navigate to="/chat" replace />} />
          </Routes>
        </main>
      </div>
      {guide && (
        <Dialog title={t("beforeBegin")} onClose={() => {}} dismissable={false}>
          <p className="prose">{t("visibility")}</p>
          <p>{t("helpBody")}</p>
          <button
            className="primary"
            onClick={() => {
              try {
                sessionStorage.setItem(`ai-learning-guide-${session.id}`, "1");
              } catch {
                /* Acknowledgement remains valid for this page. */
              }
              trackStudent("guide_completed");
              setGuide(false);
            }}
          >
            {t("understand")}
          </button>
        </Dialog>
      )}
    </div>
  );
}

function Chat({
  session,
  availability,
  refreshAvailability,
  online,
}: {
  session: Session;
  availability: Availability | null;
  refreshAvailability: () => Promise<void>;
  online: boolean;
}) {
  const { t, i18n } = useTranslation();
  const notify = useNotify();
  const [params, setParams] = useSearchParams();
  const target = params.get("conversation");
  const newFlag = params.get("new");
  const selectedMessage = params.get("message");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const sessions = useResource<Conversation[]>(
    "/chat/sessions" + (debounced ? "?q=" + encodeURIComponent(debounced) : ""),
  );
  const teachers = useResource<Teacher[]>("/chat/teachers");
  const saved = useResource<Favorite[]>("/chat/favorites");
  const feedbacks = useResource<Record<string, string>>(
    "/chat/learning-feedback",
  );
  const [teacherId, setTeacherId] = useState<number | null>(null);
  const [convTeacher, setConvTeacher] = useState<number | null>(null);
  const [convAvatar, setConvAvatar] = useState("");
  const [capabilities, setCapabilities] = useState<{
    image_input: boolean;
    image_output: boolean;
  } | null>(null);
  const [conversation, setConversation] = useState<number | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [draft, setDraft] = useState("");
  const [attachments, setAttachments] = useState<Attachment[]>([]);
  const attachmentsRef = useRef(attachments);
  attachmentsRef.current = attachments;
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);
  const requestNumber = useRef(0);
  const [teacherDialog, setTeacherDialog] = useState(false);
  const [renaming, setRenaming] = useState<Conversation | null>(null);
  const [removing, setRemoving] = useState<Conversation | null>(null);
  const [reporting, setReporting] = useState<number | null>(null);
  const [historyOpen, setHistoryOpen] = useState(false);
  const { run, busy: actionBusy } = useAction();
  const bottom = useRef<HTMLDivElement>(null);
  const followingLatest = useRef(true);
  const scrollGeometry = useRef("");
  const focusedMessage = useRef<string | null>(null);
  const [awayFromLatest, setAwayFromLatest] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const [jobVersion, setJobVersion] = useState(0);
  const draftKey = `ai-learning-draft-${session.id}-${target || "new"}`;
  const chosen =
    teachers.data?.find((teacher) => teacher.teacher_id === teacherId) ||
    teachers.data?.find((teacher) => teacher.selected) ||
    teachers.data?.[0];
  const existingTeacher = teachers.data?.find(
    (teacher) => teacher.teacher_id === convTeacher,
  );
  const avatarUrl = conversation
    ? existingTeacher ? existingTeacher.avatar_url : convAvatar
    : chosen?.avatar_url;
  const effectiveCaps = conversation ? capabilities : chosen?.capabilities;
  const blocked =
    availability?.resting || availability?.remaining_seconds === 0;
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(query), 250);
    return () => clearTimeout(timer);
  }, [query]);
  useEffect(() => {
    const sequence = ++requestNumber.current;
    activeRequest.current?.abort();
    activeRequest.current = null;
    followingLatest.current = true;
    scrollGeometry.current = "";
    focusedMessage.current = null;
    setAwayFromLatest(false);
    setBusy(false);
    setLoading(true);
    setError("");
    setMessages([]);
    setConversation(null);
    setConvAvatar("");
    setCapabilities(null);
    setAttachments([]);
    attachmentsRef.current.forEach((item) => URL.revokeObjectURL(item.preview));
    try {
      setDraft(sessionStorage.getItem(draftKey) || "");
    } catch {
      setDraft("");
    }
    const load = async () => {
      if (newFlag && !target) {
        setConversation(null);
        return;
      }
      if (target) {
        const id = Number(target);
        if (!Number.isSafeInteger(id) || id <= 0)
          throw new Error("conversation not found");
        const [data, caps] = await Promise.all([
          api<Message[]>(`/chat/conversations?conversation_id=${id}`),
          api<{ image_input: boolean; image_output: boolean }>(
            `/chat/sessions/${id}/capabilities`,
          ),
        ]);
        if (sequence !== requestNumber.current) return;
        setMessages(data);
        setConversation(id);
        setCapabilities(caps);
        const teacher = data[0] as Message & { teacher_id?: number | null; teacher_avatar_url?: string };
        setConvTeacher(teacher?.teacher_id ?? null);
        setConvAvatar(teacher?.teacher_avatar_url || "");
      } else {
        const latest = await api<{
          conversation_id: number | null;
          messages: Message[];
          teacher_id: number | null;
          teacher_avatar_url?: string;
          capabilities?: { image_input: boolean; image_output: boolean };
        }>("/chat/latest");
        if (sequence !== requestNumber.current) return;
        setMessages(latest.messages);
        setConversation(latest.conversation_id);
        setConvTeacher(latest.teacher_id);
        setConvAvatar(latest.teacher_avatar_url || "");
        setCapabilities(latest.capabilities || null);
      }
    };
    void load()
      .catch((e) => {
        if (sequence === requestNumber.current) setError(e.message);
      })
      .finally(() => {
        if (sequence === requestNumber.current) setLoading(false);
      });
    return () => {
      activeRequest.current?.abort();
    };
  }, [target, newFlag]);
  useEffect(() => {
    try {
      if (draft) sessionStorage.setItem(draftKey, draft);
      else sessionStorage.removeItem(draftKey);
    } catch {
      /* Text remains in the input even when browser storage is unavailable. */
    }
  }, [draft, draftKey]);
  useEffect(() => {
    if (
      selectedMessage &&
      !loading &&
      focusedMessage.current !== selectedMessage
    ) {
      focusedMessage.current = selectedMessage;
      followingLatest.current = false;
      document
        .getElementById(`message-${selectedMessage}`)
        ?.scrollIntoView({ block: "center" });
    } else if (followingLatest.current)
      bottom.current?.scrollIntoView({
        block: "end",
        behavior: "auto",
      });
  }, [messages, loading, selectedMessage]);
  useEffect(() => {
    const resize = () => {
      if (followingLatest.current)
        bottom.current?.scrollIntoView({ block: "end" });
    };
    window.addEventListener("resize", resize);
    window.visualViewport?.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      window.visualViewport?.removeEventListener("resize", resize);
    };
  }, []);
  useEffect(
    () => () => {
      activeRequest.current?.abort();
      attachmentsRef.current.forEach((item) =>
        URL.revokeObjectURL(item.preview),
      );
    },
    [],
  );
  useEffect(() => {
    const jobs = messages.filter(
      (message) =>
        message.image_job &&
        ["queued", "running"].includes(message.image_job.state),
    );
    if (!jobs.length) return;
    let active = true;
    const timer = setTimeout(() => {
      void Promise.all(
        jobs.map(async (message) => {
          const job = await api<ImageJob>(
            `/chat/image-jobs/${message.image_job!.id}`,
          );
          if (active)
            setMessages((rows) =>
              rows.map((row) =>
                row.id === message.id
                  ? {
                      ...row,
                      image_job: job,
                      content_blocks: job.content_blocks || row.content_blocks,
                    }
                  : row,
              ),
            );
        }),
      )
        .catch((e) => {
          if (active) notify(e.message, true);
        })
        .finally(() => {
          if (active) setJobVersion((value) => value + 1);
        });
    }, 2500);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [
    messages
      .map((message) => `${message.id}:${message.image_job?.state}`)
      .join(","),
    jobVersion,
  ]);
  const select = (id: number | null) => {
    setHistoryOpen(false);
    setParams(id ? { conversation: String(id) } : { new: crypto.randomUUID() });
  };
  const send = async (retry?: Message, followUp?: string) => {
    if (activeRequest.current || busy || blocked || !online || loading) return;
    const text = retry ? retry.content : (followUp ?? draft.trim());
    const assets = retry
      ? (retry.content_blocks || [])
          .filter((block) => block.type === "image")
          .map((block) => block.asset_id!)
      : followUp
        ? []
        : (attachments
            .map((item) => item.asset?.asset_id)
            .filter(Boolean) as string[]);
    if (
      (!text && !assets.length) ||
      attachments.some((item) => item.status !== "ready")
    )
      return;
    const controller = new AbortController();
    followingLatest.current = true;
    setAwayFromLatest(false);
    activeRequest.current = controller;
    const sequence = requestNumber.current;
    setBusy(true);
    setError("");
    let cid = conversation;
    let userId: number | null = retry?.id || null;
    let pendingId = -Date.now();
    let persisted = false;
    if (!retry)
      setMessages((rows) => [
        ...rows,
        {
          id: pendingId - 1,
          role: "user",
          content: text,
          content_blocks: followUp
            ? []
            : attachments.map((row) => row.asset!).filter(Boolean),
          fence_action: "pending",
          created_at: new Date().toISOString(),
        },
      ]);
    setMessages((rows) => [
      ...rows,
      {
        id: pendingId,
        role: "assistant",
        content: "",
        content_blocks: [],
        fence_action: "pending",
        created_at: new Date().toISOString(),
      },
    ]);
    trackStudent("question_submitted");
    try {
      await stream(
        {
          content: text,
          asset_ids: assets,
          conversation_id: conversation,
          teacher_id: conversation ? convTeacher : (chosen?.teacher_id ?? null),
          locale: i18n.language,
          ...(retry ? { retry_message_id: retry.id } : {}),
        },
        controller.signal,
        (name, data) => {
          if (sequence !== requestNumber.current) return;
          if (name === "meta") {
            cid = Number(data.conversation_id);
            userId = Number(data.user_message_id);
            persisted = true;
            setConversation(cid);
            setConvTeacher(
              conversation ? convTeacher : (chosen?.teacher_id ?? null),
            );
            if (!conversation) setConvAvatar(chosen?.avatar_url || "");
            setMessages((rows) =>
              rows.map((row) =>
                row.id === pendingId - 1
                  ? {
                      ...row,
                      id: userId!,
                      fence_action: String(data.fence_action),
                    }
                  : row.id === pendingId
                    ? { ...row, fence_action: String(data.fence_action) }
                    : row,
              ),
            );
            if (!retry && !followUp) {
              setDraft("");
              try {
                sessionStorage.removeItem(draftKey);
              } catch {
                /* Draft storage unavailable. */
              }
              attachments.forEach((item) => URL.revokeObjectURL(item.preview));
              setAttachments([]);
            }
          }
          if (name === "delta" || name === "replace")
            setMessages((rows) =>
              rows.map((row) =>
                row.id === pendingId
                  ? {
                      ...row,
                      content:
                        name === "replace"
                          ? String(data.text)
                          : row.content + String(data.text),
                    }
                  : row,
              ),
            );
          if (name === "done") trackStudent("answer_received");
          if (name === "done")
            setMessages((rows) =>
              rows.map((row) =>
                row.id === pendingId
                  ? {
                      ...row,
                      id: Number(data.message_id),
                      image_job: data.image_job as ImageJob | undefined,
                    }
                  : row,
              ),
            );
        },
      );
    } catch (e) {
      trackStudent(e instanceof DOMException && e.name === "AbortError" ? "answer_cancelled" : "answer_failed");
      if (sequence === requestNumber.current) {
        const message =
          e instanceof DOMException && e.name === "AbortError"
            ? t("stopped")
            : e instanceof Error
              ? e.message
              : t("error");
        setError(message);
        if (!persisted && !retry)
          setMessages((rows) =>
            rows.filter(
              (row) => row.id !== pendingId && row.id !== pendingId - 1,
            ),
          );
      }
    } finally {
      if (sequence === requestNumber.current) {
        setBusy(false);
        activeRequest.current = null;
        sessions.reload();
        saved.reload();
        feedbacks.reload();
        void refreshAvailability().catch(() => {});
        if (cid && persisted) {
          const data = await api<Message[]>(
            `/chat/conversations?conversation_id=${cid}`,
          ).catch(() => null);
          if (data && sequence === requestNumber.current) setMessages(data);
          if (!target && !followUp)
            setParams({ conversation: String(cid) }, { replace: true });
        }
      }
    }
  };
  const last = messages.at(-1);
  const failedQuestion =
    !busy &&
    last?.role === "user" &&
    ["failed", "pending"].includes(last.fence_action || "")
      ? last
      : null;
  return (
    <div className="learning-workspace">
      <aside className={`history-sidebar ${historyOpen ? "open" : ""}`}>
        <button
          className="primary"
          onClick={() => select(null)}
          disabled={busy}
        >
          + {t("newChat")}
        </button>
        <input
          type="search"
          aria-label={t("searchHint")}
          placeholder={t("searchHint")}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <ResourceState {...sessions} retry={sessions.reload} />
        {sessions.data && !sessions.data.length && <Empty />}
        {sessions.data?.map((row) => (
          <div
            className={`history-row ${conversation === row.conversation_id ? "current" : ""}`}
            key={row.conversation_id}
          >
            <button
              className="history-title"
              onClick={() => select(row.conversation_id!)}
              disabled={busy}
            >
              <strong>
                {row.pinned ? "⌃ " : ""}
                {row.title}
              </strong>
              <small>{date(row.last_time, session.timezone)}</small>
            </button>
            <div className="history-tools">
              <button
                disabled={busy || actionBusy}
                onClick={() => setRenaming(row)}
              >
                {t("rename")}
              </button>
              <button
                disabled={busy || actionBusy}
                onClick={() =>
                  void run(async () => {
                    await api(
                      `/chat/sessions/${row.conversation_id}/pin`,
                      "PUT",
                      { pinned: !row.pinned },
                    );
                    sessions.reload();
                  })
                }
              >
                {t(row.pinned ? "unpin" : "pin")}
              </button>
              <button
                disabled={busy || actionBusy}
                onClick={() => setRemoving(row)}
              >
                {t("remove")}
              </button>
            </div>
          </div>
        ))}
      </aside>
      <section className="chat-panel">
        <header className="chat-header">
          <button
            className="history-toggle"
            onClick={() => setHistoryOpen((value) => !value)}
            aria-expanded={historyOpen}
          >
            {t("conversationHistory")}
          </button>
          <button
            className="teacher-select"
            onClick={() => setTeacherDialog(true)}
            disabled={busy}
          >
            <TeacherAvatar url={avatarUrl} />
            <span>
              {conversation
                ? contentText(
                    existingTeacher?.name ||
                      sessions.data?.find(
                        (row) => row.conversation_id === conversation,
                      )?.teacher_name ||
                      t("teacher"),
                  )
                : contentText(chosen?.name || t("teacher"))}
            </span>
            <ChevronDown size={17} />
          </button>
        </header>
        <div
          className="message-scroll"
          onFocusCapture={() => {
            followingLatest.current = false;
          }}
          onWheel={(event) => {
            if (event.deltaY < 0) followingLatest.current = false;
          }}
          onTouchMove={() => {
            followingLatest.current = false;
          }}
          onPointerDown={(event) => {
            if (event.target === event.currentTarget)
              followingLatest.current = false;
          }}
          onKeyDown={(event) => {
            if (["ArrowUp", "PageUp", "Home"].includes(event.key))
              followingLatest.current = false;
          }}
          onLoadCapture={() => {
            if (followingLatest.current)
              bottom.current?.scrollIntoView({ block: "end" });
          }}
          onScroll={(event) => {
            const area = event.currentTarget;
            const nearBottom =
              area.scrollHeight - area.scrollTop - area.clientHeight < 64;
            const geometry = `${area.clientWidth}:${area.clientHeight}:${area.scrollHeight}`;
            const layoutChanged = scrollGeometry.current !== geometry;
            scrollGeometry.current = geometry;
            if (layoutChanged && followingLatest.current && !nearBottom) {
              area.scrollTop = area.scrollHeight;
              return;
            }
            followingLatest.current = nearBottom;
            setAwayFromLatest(!nearBottom);
          }}
        >
          <ResourceState loading={loading} error={null} retry={() => {}} />
          {!loading && !messages.length && (
            <div className="chat-welcome">
              <Sparkles size={32} />
              <h1>{t("newConversation")}</h1>
              <p>{t("topicHint")}</p>
            </div>
          )}
          {messages.map((message) => (
            <div id={`message-${message.id}`} key={message.id}>
              <MessageCard
                message={message}
                teacher={conversation ? existingTeacher?.name : chosen?.name}
                teacherAvatar={avatarUrl || ""}
                saved={saved.data?.some((row) => row.message_id === message.id)}
                feedback={feedbacks.data?.[String(message.id)]}
                busy={actionBusy || busy}
                onSave={
                  message.id > 0
                    ? () =>
                        void run(async () => {
                          const existing = saved.data?.find(
                            (row) => row.message_id === message.id,
                          );
                          if (existing)
                            await api(
                              `/chat/favorites/${existing.id}`,
                              "DELETE",
                            );
                          else
                            await api("/chat/favorites", "POST", {
                              message_id: message.id,
                            });
                          saved.reload();
                        }, t("changed"))
                    : undefined
                }
                onReport={
                  message.id > 0 ? () => setReporting(message.id) : undefined
                }
                onFeedback={
                  message.id > 0
                    ? (action) =>
                        void run(async () => {
                          const sequence = requestNumber.current;
                          const result = await api<{ changed: boolean }>(
                            `/chat/messages/${message.id}/learning-feedback`,
                            "POST",
                            { action },
                          );
                          feedbacks.reload();
                          if (
                            action !== "understood" &&
                            result.changed &&
                            sequence === requestNumber.current
                          ) {
                            const instruction = tx(
                              action === "not_understood"
                                ? "我还不懂，请降低难度，用更简单的例子换一种方式讲解"
                                : "请沿用当前方式继续讲解，补充步骤和例子",
                            );
                            await send(
                              undefined,
                              `${instruction}\n\n${message.content.slice(0, 3500)}`,
                            );
                          }
                        }, t("changed"))
                    : undefined
                }
                onDiagram={
                  effectiveCaps?.image_output && message.id > 0
                    ? () =>
                        void run(async () => {
                          const requested = await api<ImageJob>(
                            `/chat/messages/${message.id}/diagram`,
                            "POST",
                            { locale: i18n.language },
                          );
                          const job =
                            requested.state === "ready"
                              ? await api<ImageJob>(
                                  `/chat/image-jobs/${requested.id}`,
                                )
                              : requested;
                          setMessages((rows) =>
                            rows.map((row) =>
                              row.id === message.id
                                ? {
                                    ...row,
                                    image_job: job,
                                    content_blocks:
                                      job.content_blocks || row.content_blocks,
                                  }
                                : row,
                            ),
                          );
                        })
                    : undefined
                }
              />
              {message.id < 0 &&
                message.role === "assistant" &&
                !message.content && (
                  <p className="muted" role="status">
                    {t("loadingAnswer")}
                  </p>
                )}
            </div>
          ))}
          {error && (
            <div className="notice error" role="alert">
              {tx(error)}
            </div>
          )}
          {failedQuestion && (
            <button
              disabled={blocked || actionBusy || !online}
              onClick={() => void send(failedQuestion)}
            >
              {t("retry")}
            </button>
          )}
          <div ref={bottom} />
        </div>
        <div className="composer-area">
          {awayFromLatest && (
            <button
              className="back-to-latest"
              onClick={() => {
                followingLatest.current = true;
                setAwayFromLatest(false);
                bottom.current?.scrollIntoView({ block: "end" });
              }}
            >
              {t("backToLatest")}
            </button>
          )}
          {blocked ? (
            <div className="rest-notice" role="status">
              <h2>{t(availability?.resting ? "takeBreak" : "timeUp")}</h2>
              <p>
                {availability?.resting
                  ? t("quietPeriod", {
                      start: availability.quiet_start + ":00",
                      end: availability.quiet_end + ":00",
                    })
                  : t("breakHint")}
              </p>
              <small>
                {availability?.timezone} · {t("draftSaved")}
              </small>
              <button onClick={() => void run(refreshAvailability)}>
                {t("checkAgain")}
              </button>
            </div>
          ) : (
            <form
              className="composer"
              onSubmit={(event) => {
                event.preventDefault();
                void send();
              }}
            >
              <textarea
                ref={input}
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                placeholder={t("ask")}
                aria-label={t("ask")}
                maxLength={4000}
                rows={2}
                disabled={busy || loading}
                onKeyDown={(event) => {
                  if (
                    event.key === "Enter" &&
                    !event.shiftKey &&
                    !event.nativeEvent.isComposing &&
                    event.keyCode !== 229
                  ) {
                    event.preventDefault();
                    void send();
                  }
                }}
              />
              <div className="composer-tools">
                {effectiveCaps?.image_input ? (
                  <PhotoPicker
                    attachments={attachments}
                    setAttachments={setAttachments}
                    conversation={conversation}
                    teacher={
                      conversation ? convTeacher : (chosen?.teacher_id ?? null)
                    }
                    disabled={busy || loading}
                  />
                ) : (
                  <span className="muted composer-hint">{t("inputHint")}</span>
                )}
                <div className="send-control">
                  {busy ? (
                    <button
                      type="button"
                      className="send-button"
                      onClick={() => activeRequest.current?.abort()}
                      aria-label={t("stop")}
                    >
                      <Square size={18} />
                    </button>
                  ) : (
                    <button
                      className="send-button"
                      aria-label={t("send")}
                      disabled={
                        loading ||
                        actionBusy ||
                        !online ||
                        (!draft.trim() && !attachments.length) ||
                        attachments.some((row) => row.status !== "ready") ||
                        !chosen ||
                        (chosen.access !== "available" && !conversation)
                      }
                    >
                      <ArrowUp size={23} />
                    </button>
                  )}
                </div>
              </div>
            </form>
          )}
          <p className="composer-disclosure">{t("visibility")}</p>
        </div>
      </section>
      {teacherDialog && (
        <Dialog title={t("teachers")} onClose={() => setTeacherDialog(false)}>
          <p>{t("newTeacherHint")}</p>
          <ResourceState {...teachers} retry={teachers.reload} />
          {teachers.data?.length === 0 && <Empty>{t("noTeachers")}</Empty>}
          {teachers.data?.map((teacher) => (
            <button
              className="teacher-option"
              key={teacher.teacher_id ?? "default"}
              disabled={actionBusy || teacher.access !== "available"}
              onClick={() =>
                void run(async () => {
                  if (teacher.teacher_id !== null)
                    await api("/chat/teachers/selection", "PUT", {
                      teacher_id: teacher.teacher_id,
                    });
                  trackStudent("teacher_selected");
                  setTeacherId(teacher.teacher_id);
                  teachers.reload();
                  select(null);
                  setTeacherDialog(false);
                })
              }
            >
              <TeacherAvatar url={teacher.avatar_url} />
              <span>
                <strong>{contentText(teacher.name)}</strong>
                <small>
                  {teacher.access === "available"
                    ? t("active")
                    : t("teacherLocked")}
                </small>
              </span>
            </button>
          ))}
        </Dialog>
      )}
      {renaming && (
        <Dialog title={t("rename")} onClose={() => setRenaming(null)}>
          <form
            onSubmit={(event) => {
              const data = formData(event);
              void run(async () => {
                await api(
                  `/chat/sessions/${renaming.conversation_id}`,
                  "PATCH",
                  data,
                );
                sessions.reload();
                setRenaming(null);
              }, t("changed"));
            }}
          >
            <Field label={t("title")}>
              <input
                name="title"
                defaultValue={renaming.title}
                maxLength={100}
                required
              />
            </Field>
            <button className="primary" disabled={actionBusy}>
              {t("save")}
            </button>
          </form>
        </Dialog>
      )}
      {removing && (
        <Confirm
          title={t("remove")}
          hint={t("deleteChat")}
          onClose={() => setRemoving(null)}
          action={async () => {
            await api(`/chat/sessions/${removing.conversation_id}`, "DELETE");
            sessions.reload();
            if (conversation === removing.conversation_id) select(null);
          }}
        />
      )}
      {reporting && (
        <Dialog title={t("report")} onClose={() => setReporting(null)}>
          <form
            onSubmit={(event) => {
              const data = formData(event);
              void run(async () => {
                await api("/chat/reports", "POST", {
                  message_id: reporting,
                  reason: data.reason,
                });
                setReporting(null);
              }, t("changed"));
            }}
          >
            <Field label={t("reason")}>
              <textarea name="reason" required minLength={1} maxLength={500} />
            </Field>
            <button className="primary" disabled={actionBusy}>
              {t("submit")}
            </button>
          </form>
        </Dialog>
      )}
    </div>
  );
}

function StudentStats() {
  const { t } = useTranslation();
  const resource = useResource<Stats>("/chat/my-stats");
  return (
    <>
      <Heading title={t("activity")} />
      <ResourceState {...resource} retry={resource.reload} />
      {resource.data && (
        <>
          {(["today", "week"] as const).map((period) => (
            <section className="panel" key={period}>
              <h2>{t(period === "today" ? "today" : "thisWeek")}</h2>
              <div className="metrics">
                <section>
                  <span>{t("questions")}</span>
                  <strong>{number(resource.data![period].questions)}</strong>
                </section>
                <section>
                  <span>{t("learningTime")}</span>
                  <strong>
                    {number(resource.data![period].minutes)}{" "}
                    <small>{t("minutes")}</small>
                  </strong>
                </section>
              </div>
            </section>
          ))}
          <section className="panel">
            <h2>{t("favorites")}</h2>
            <strong>{number(resource.data.favorites || 0)}</strong>
          </section>
        </>
      )}
    </>
  );
}
type Report = {
  id: number;
  content: string;
  conversation_id: number | null;
  message_id: number;
  reason: string;
  status: string;
  reply: string;
  created_at: string;
  reviewed_at: string | null;
};
function Reports({
  source,
  timezone,
}: {
  source: (conversation: number, message?: number) => void;
  timezone: string | null;
}) {
  const { t } = useTranslation();
  const resource = useResource<Report[]>("/chat/reports");
  return (
    <>
      <Heading title={t("reports")} />
      <ResourceState {...resource} retry={resource.reload} />
      {resource.data?.length === 0 && <Empty />}
      {resource.data?.map((row) => (
        <article className="panel" key={row.id}>
          <header className="section-heading">
            <strong>{date(row.created_at, timezone)}</strong>
            <span className="badge">{t(row.status)}</span>
          </header>
          <p>{row.reason}</p>
          <blockquote>{row.content}</blockquote>
          {row.reply && <p className="notice">{row.reply}</p>}
          {row.conversation_id && (
            <button
              onClick={() => source(row.conversation_id!, row.message_id)}
            >
              {t("source")}
            </button>
          )}
        </article>
      ))}
    </>
  );
}
