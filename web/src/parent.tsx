import { useEffect, useState } from "react";
import {
  NavLink,
  Navigate,
  Route,
  Routes,
  useNavigate,
  useParams,
} from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutDashboard,
  Users,
  MessagesSquare,
  Clock3,
  CreditCard,
  Bell,
  Settings,
  BookOpen,
  Bookmark,
  GraduationCap,
  Sparkles,
  X,
} from "lucide-react";
import {
  api,
  type Session,
  type Family,
  type Child,
  type Stats,
  type Message,
  type Conversation,
  type FamilySettings,
} from "./api";
import {
  AccountSettings,
  Brand,
  Confirm,
  copy,
  Dialog,
  download,
  Empty,
  Field,
  formData,
  Heading,
  LanguagePicker,
  MenuButton,
  useNarrowNav,
  ResourceState,
  useAction,
  useResource,
} from "./ui";
import { date, number, tx, contentText } from "./i18n";
import { Favorites, MessageCard } from "./content";
import Grades from "./grades";
import Learning from "./learning";
import Assessments from "./assessments";
import PaddleSandbox from "./paddle-sandbox";

type PageProps = {
  family: Family;
  child: Child | undefined;
  reload: () => void;
  choose: (id: number) => void;
};
export default function Parent({
  session,
  refresh,
}: {
  session: Session;
  refresh: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const resource = useResource<Family>("/parent/family");
  const navigate = useNavigate();
  const [selected, setSelected] = useState<number | null>(null);
  const [menu, setMenu] = useState(false);
  const narrow = useNarrowNav();
  const family = resource.data;
  const child =
    family?.students.find((row) => row.id === selected) ||
    family?.students.find((row) => row.active) ||
    family?.students[0];
  const choose = (id: number) => {
    setSelected(id);
    try {
      sessionStorage.setItem(
        `ai-learning-child-${session.family_id}`,
        String(id),
      );
    } catch {
      /* Selection still works without storage. */
    }
  };
  useEffect(() => {
    try {
      const id = Number(
        sessionStorage.getItem(`ai-learning-child-${session.family_id}`),
      );
      if (id) setSelected(id);
    } catch {
      /* No persistent selection. */
    }
  }, [session.family_id]);
  const nav = [
    ["/", "overview", LayoutDashboard],
    ["/children", "children", Users],
    ["/activity", "activity", MessagesSquare],
    ["/schedule", "schedule", Clock3],
    ["/favorites", "favorites", Bookmark],
    ["/learning", "learning", Sparkles],
    ["/grades", "grades", GraduationCap],
    ["/assessments", "assessments", BookOpen],
    ["/notifications", "notifications", Bell],
    ["/subscription", "subscription", CreditCard],
    ["/settings", "settings", Settings],
  ] as const;
  const source = (conversation: number, message?: number | null) => {
    void navigate(
      `/activity/${conversation}${message ? "#message-" + message : ""}`,
    );
  };
  return (
    <div className="app-shell">
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
        <span className="eyebrow">{t("parentSpace")}</span>
        <nav aria-label={t("parentSpace")}>
          {nav.map(([path, key, Icon]) => (
            <NavLink
              key={path}
              to={path}
              end={path === "/"}
              onClick={() => setMenu(false)}
            >
              <Icon size={19} aria-hidden="true" />
              {t(key)}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-profile">{session.nickname}</div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <MenuButton onClick={() => setMenu((v) => !v)} />
          <small>{t("parentSpace")}</small>
          <div className="topbar-end">
            <LanguagePicker />
            <NavLink
              className="icon-button"
              to="/notifications"
              aria-label={t("notifications")}
            >
              <Bell size={20} />
            </NavLink>
          </div>
        </header>
        <main id="main-content" className="page-content">
          <ResourceState {...resource} retry={resource.reload} />
          {family && (
            <>
              {family.students.length > 0 && (
                <div className="child-switcher">
                  <Field label={t("chooseChild")}>
                    <select
                      value={child?.id || ""}
                      onChange={(event) => choose(Number(event.target.value))}
                    >
                      {family.students.map((row) => (
                        <option key={row.id} value={row.id}>
                          {row.nickname}
                          {row.active ? "" : ` (${t("inactive")})`}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <small>
                    {family.timezone || t("familyTimezone") + ": —"}
                  </small>
                </div>
              )}
              <Routes>
                <Route
                  path="/"
                  element={
                    <Overview
                      family={family}
                      child={child}
                      reload={resource.reload}
                      choose={choose}
                    />
                  }
                />
                <Route
                  path="/children"
                  element={
                    <Children
                      family={family}
                      child={child}
                      reload={resource.reload}
                      choose={choose}
                    />
                  }
                />
                <Route
                  path="/activity"
                  element={<Activity child={child} source={source} />}
                />
                <Route
                  path="/activity/:conversationId"
                  element={<Review timezone={family.timezone} />}
                />
                <Route
                  path="/schedule"
                  element={
                    <Schedule
                      family={family}
                      reload={resource.reload}
                      refresh={refresh}
                    />
                  }
                />
                <Route
                  path="/favorites"
                  element={
                    child ? (
                      <>
                        <Heading title={t("favorites")} />
                        <Favorites
                          key={child.id}
                          path={`/parent/students/${child.id}/favorites`}
                          onSource={source}
                        />
                      </>
                    ) : (
                      <Empty>{t("noChildren")}</Empty>
                    )
                  }
                />
                <Route
                  path="/learning"
                  element={
                    child ? (
                      <>
                        <Heading title={t("learning")} />
                        <Learning
                          key={child.id}
                          prefix={`/parent/students/${child.id}`}
                        />
                      </>
                    ) : (
                      <Empty>{t("noChildren")}</Empty>
                    )
                  }
                />
                <Route
                  path="/grades"
                  element={
                    child ? (
                      <>
                        <Heading title={t("grades")} />
                        <Grades
                          key={child.id}
                          prefix={`/parent/students/${child.id}`}
                          timezone={family.timezone}
                        />
                      </>
                    ) : (
                      <Empty>{t("noChildren")}</Empty>
                    )
                  }
                />
                <Route
                  path="/assessments"
                  element={
                    child ? (
                      <>
                        <Heading title={t("assessments")} />
                        <Assessments
                          key={child.id}
                          prefix={`/parent/students/${child.id}`}
                          timezone={family.timezone}
                          onSource={source}
                        />
                      </>
                    ) : (
                      <Empty>{t("noChildren")}</Empty>
                    )
                  }
                />
                <Route
                  path="/notifications"
                  element={
                    <Notifications
                      source={(conversation, childId) => {
                        if (childId) choose(childId);
                        source(conversation);
                      }}
                      timezone={family.timezone}
                    />
                  }
                />
                <Route
                  path="/subscription"
                  element={<Subscription timezone={family.timezone} />}
                />
                <Route
                  path="/settings"
                  element={
                    <AccountSettings
                      session={session}
                      refresh={async () => {
                        await refresh();
                        resource.reload();
                      }}
                    />
                  }
                />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </>
          )}
        </main>
      </div>
    </div>
  );
}

function Overview({ family, child }: PageProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const stats = useResource<Stats>(
    child ? `/parent/students/${child.id}/summary` : null,
  );
  const conversations = useResource<Conversation[]>(
    child ? `/parent/students/${child.id}/conversations?status=active` : null,
  );
  return (
    <>
      <Heading
        title={t("welcome")}
        hint={t("overviewHint")}
        actions={
          <button className="primary" onClick={() => navigate("/children")}>
            + {t("connectDevice")}
          </button>
        }
      />
      {!family.timezone && (
        <div className="notice">
          <p>{t("setupHint")}</p>
          <button onClick={() => navigate("/schedule")}>
            {t("familyTimezone")}
          </button>
        </div>
      )}
      {!child ? (
        <section className="panel">
          <h2>{t("createFamily")}</h2>
          <p>{t("noChildren")}</p>
          <button className="primary" onClick={() => navigate("/children")}>
            {t("addChild")}
          </button>
        </section>
      ) : (
        <>
          <ResourceState {...stats} retry={stats.reload} />
          {stats.data && (
            <div className="metrics">
              <section>
                <span>{t("learningTime")}</span>
                <strong>
                  {number(stats.data.today.minutes)}{" "}
                  <small>{t("minutes")}</small>
                </strong>
                <small>
                  {family.settings.daily_minutes_cap
                    ? `${number(family.settings.daily_minutes_cap)} ${t("minutes")}`
                    : t("unlimited")}
                </small>
              </section>
              <section>
                <span>{t("questions")}</span>
                <strong>{number(stats.data.today.questions)}</strong>
              </section>
              <section>
                <span>{t("thisWeek")}</span>
                <strong>
                  {number(stats.data.week.active_days)}{" "}
                  <small>{t("activeDays")}</small>
                </strong>
              </section>
            </div>
          )}
          <div className="overview-grid">
            <section className="panel">
              <header className="section-heading">
                <h2>{t("recent")}</h2>
                <NavLink to="/activity">{t("viewAll")} →</NavLink>
              </header>
              <ResourceState {...conversations} retry={conversations.reload} />
              {conversations.data && !conversations.data.length && <Empty />}
              {conversations.data?.slice(0, 5).map((row) => (
                <button
                  className="conversation-row"
                  key={row.id}
                  onClick={() => navigate(`/activity/${row.id}`)}
                >
                  <MessagesSquare size={19} />
                  <span>
                    <strong>{row.title}</strong>
                    <small>
                      {contentText(row.teacher_name)} ·{" "}
                      {date(row.created_at, family.timezone)}
                    </small>
                  </span>
                  <span>→</span>
                </button>
              ))}
            </section>
            <section className="balance-panel">
              <Clock3 />
              <h2>{t("schedule")}</h2>
              <p>
                {stats.data &&
                  (family.settings.daily_minutes_cap
                    ? t("remaining", {
                        count: Math.max(
                          0,
                          family.settings.daily_minutes_cap -
                            Math.ceil(
                              (stats.data.today.quota_used_seconds ??
                                stats.data.today.minutes * 60) / 60,
                            ),
                        ),
                      })
                    : t("unlimited"))}
              </p>
              {family.settings.daily_minutes_cap > 0 && (
                <progress
                  max={family.settings.daily_minutes_cap}
                  value={stats.data?.today.minutes || 0}
                />
              )}
              {family.settings.quiet_enabled && (
                <p>
                  {t("quietPeriod", {
                    start: family.settings.quiet_start + ":00",
                    end: family.settings.quiet_end + ":00",
                  })}
                </p>
              )}
              <small>{family.timezone}</small>
              <button onClick={() => navigate("/schedule")}>{t("edit")}</button>
            </section>
          </div>
          <p className="notice">{t("parentVisibility")}</p>
        </>
      )}
    </>
  );
}

type Device = {
  id: number;
  device_name: string;
  is_current: boolean;
  bound_at: string;
  last_seen_at: string | null;
  revoked_at: string | null;
};
type Code = { bind_code: string; expires_at: string; student_id: number };
function Children({ family, child, reload, choose }: PageProps) {
  const { t } = useTranslation();
  const { run, busy } = useAction();
  const [adding, setAdding] = useState(false);
  const [editing, setEditing] = useState<Child | null>(null);
  const [connecting, setConnecting] = useState<Child | null>(null);
  const [code, setCode] = useState<Code | null>(null);
  const [removing, setRemoving] = useState<Child | null>(null);
  const [disconnect, setDisconnect] = useState<Device | null>(null);
  const [time, setTime] = useState(Date.now());
  const devices = useResource<Device[]>(
    child ? `/parent/students/${child.id}/devices` : null,
  );
  useEffect(() => {
    if (!code) return;
    const timer = setInterval(() => setTime(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [code]);
  const expired =
    code &&
    new Date(
      /Z$|[+-]\d{2}:\d{2}$/.test(code.expires_at)
        ? code.expires_at
        : code.expires_at + "Z",
    ).getTime() <= time;
  const generateCode = async (target: Child) => {
    const data = await api<Code>(
      `/parent/students/${target.id}/rebind-code`,
      "POST",
    );
    setCode(data);
    setConnecting(null);
  };
  return (
    <>
      <Heading
        title={t("children")}
        hint={t("nameHint")}
        actions={
          <button
            className="primary"
            disabled={!family.timezone}
            onClick={() => setAdding(true)}
          >
            {t("addChild")}
          </button>
        }
      />
      {!family.timezone && (
        <p className="notice">
          {t("setupHint")}{" "}
          <NavLink to="/schedule">{t("familyTimezone")} →</NavLink>
        </p>
      )}
      {!family.students.length && <Empty>{t("noChildren")}</Empty>}
      {family.students.map((row) => (
        <section
          className={`panel child-card ${row.id === child?.id ? "selected-child" : ""}`}
          key={row.id}
        >
          <div>
            <h2>{row.nickname}</h2>
            <p>
              {row.grade_band} · {t("ageBand")} ·{" "}
              {t(row.active ? "active" : "inactive")}
            </p>
            <small>{row.current_device?.name || t("noDevice")}</small>
          </div>
          <div className="actions">
            <button onClick={() => choose(row.id)}>{t("details")}</button>
            {row.active && (
              <>
                <button onClick={() => setEditing(row)}>{t("edit")}</button>
                <button onClick={() => setConnecting(row)}>
                  {t("connectDevice")}
                </button>
                <button onClick={() => setRemoving(row)}>{t("remove")}</button>
              </>
            )}
          </div>
        </section>
      ))}
      {child && (
        <section className="panel">
          <h2>
            {child.nickname} · {t("currentDevice")}
          </h2>
          <ResourceState {...devices} retry={devices.reload} />
          {devices.data && !devices.data.length && (
            <Empty>{t("noDevice")}</Empty>
          )}
          {devices.data?.map((device) => (
            <article className="device-row" key={device.id}>
              <div>
                <strong>{device.device_name}</strong>
                <p>
                  {t(device.is_current ? "active" : "inactive")} ·{" "}
                  {date(
                    device.last_seen_at || device.bound_at,
                    family.timezone,
                  )}
                </p>
              </div>
              {device.is_current && (
                <button onClick={() => setDisconnect(device)}>
                  {t("disconnect")}
                </button>
              )}
            </article>
          ))}
          <div className="actions">
            <button
              disabled={busy}
              onClick={() =>
                void run(async () =>
                  download(
                    await api(`/parent/students/${child.id}/export`),
                    `learning-${child.id}.json`,
                  ),
                )
              }
            >
              {t("export")}
            </button>
          </div>
          <Usage child={child} />
          <BoundarySettings child={child} reload={reload} />
        </section>
      )}
      {(adding || editing) && (
        <Dialog
          title={t(adding ? "addChild" : "edit")}
          onClose={() => {
            setAdding(false);
            setEditing(null);
          }}
        >
          <form
            onSubmit={(event) => {
              const data = formData(event);
              void run(async () => {
                if (adding) {
                  const created = await api<Code>(
                    "/parent/students",
                    "POST",
                    data,
                  );
                  setCode(created);
                  choose(created.student_id);
                } else if (editing) {
                  await api(`/parent/students/${editing.id}/nickname`, "PUT", {
                    nickname: data.nickname,
                  });
                  await api(
                    `/parent/students/${editing.id}/grade-band`,
                    "PUT",
                    { grade_band: data.grade_band },
                  );
                }
                setAdding(false);
                setEditing(null);
                reload();
              }, t("changed"));
            }}
          >
            <Field label={t("nickname")} hint={t("nameHint")}>
              <input
                name="nickname"
                required
                maxLength={50}
                defaultValue={editing?.nickname}
              />
            </Field>
            <Field label={t("ageBand")}>
              <select
                name="grade_band"
                defaultValue={editing?.grade_band || "8-12"}
              >
                {["8-12", "12-16", "16-18"].map((band) => (
                  <option key={band}>{band}</option>
                ))}
              </select>
            </Field>
            <button className="primary" disabled={busy}>
              {t("save")}
            </button>
          </form>
        </Dialog>
      )}
      {connecting && (
        <Confirm
          title={t("connectDevice")}
          hint={t("replaceWarning")}
          onClose={() => setConnecting(null)}
          action={() => generateCode(connecting)}
        />
      )}
      {code && (
        <Dialog title={t("connectDevice")} onClose={() => setCode(null)}>
          <p>{t("codeHelp")}</p>
          <div className={`connection-code ${expired ? "expired" : ""}`}>
            <code>
              {code.bind_code.slice(0, 4)} {code.bind_code.slice(4)}
            </code>
          </div>
          <p>
            {t("validUntil")}: {date(code.expires_at, family.timezone)}
          </p>
          {expired && (
            <p className="notice error" role="alert">
              {t("expiredCode")}
            </p>
          )}
          <div className="actions">
            <button
              disabled={busy || !!expired}
              onClick={() => void run(() => copy(code.bind_code), t("copied"))}
            >
              {t("copy")}
            </button>
            <button
              disabled={busy}
              onClick={() =>
                void run(async () => {
                  setCode(
                    await api<Code>(
                      `/parent/students/${code.student_id}/rebind-code`,
                      "POST",
                    ),
                  );
                })
              }
            >
              {t("newCode")}
            </button>
          </div>
          <p className="notice">{t("replaceWarning")}</p>
        </Dialog>
      )}
      {removing && (
        <Confirm
          title={t("releaseChild")}
          hint={t("dataKept")}
          onClose={() => setRemoving(null)}
          action={async () => {
            await api(`/parent/students/${removing.id}`, "DELETE");
            reload();
          }}
        />
      )}
      {disconnect && child && (
        <Confirm
          title={t("disconnect")}
          hint={disconnect.device_name}
          onClose={() => setDisconnect(null)}
          action={async () => {
            await api(
              `/parent/students/${child.id}/devices/${disconnect.id}/revoke`,
              "POST",
            );
            devices.reload();
            reload();
          }}
        />
      )}
    </>
  );
}

function Usage({ child }: { child: Child }) {
  const { t } = useTranslation();
  const resource = useResource<{
    today: { tokens_in: number; tokens_out: number };
    total: { tokens_in: number; tokens_out: number };
  }>(`/parent/students/${child.id}/usage`);
  return (
    <section className="boundary-form">
      <h2>{t("modelUsage")}</h2>
      <ResourceState {...resource} retry={resource.reload} />
      {resource.data && (
        <dl>
          {(["today", "total"] as const).map((period) => (
            <div key={period}>
              <dt>{t(period === "today" ? "today" : "all")}</dt>
              <dd>
                {t("tokensIn")}: {number(resource.data![period].tokens_in)} ·{" "}
                {t("tokensOut")}: {number(resource.data![period].tokens_out)}
              </dd>
            </div>
          ))}
        </dl>
      )}
    </section>
  );
}

function BoundarySettings({
  child,
  reload,
}: {
  child: Child;
  reload: () => void;
}) {
  const { t } = useTranslation();
  const { run, busy } = useAction();
  return (
    <form
      className="boundary-form"
      key={child.id}
      onSubmit={(event) => {
        const data = formData(event);
        void run(async () => {
          await api(`/parent/students/${child.id}/fence-settings`, "PUT", {
            fence_level: data.fence_level,
            forbidden_words: data.words
              .split("\n")
              .map((word) => word.trim())
              .filter(Boolean),
          });
          reload();
        }, t("changed"));
      }}
    >
      <h2>{t("fence")}</h2>
      <Field label={t("fenceLevel")}>
        <select
          name="fence_level"
          defaultValue={child.fence_settings.fence_level}
        >
          {["strict", "relaxed", "off"].map((level) => (
            <option key={level} value={level}>
              {t(level)}
            </option>
          ))}
        </select>
      </Field>
      <Field label={t("forbidden")} hint={t("forbiddenHint")}>
        <textarea
          name="words"
          defaultValue={child.fence_settings.forbidden_words.join("\n")}
          maxLength={50500}
        />
      </Field>
      <button className="primary" disabled={busy || !child.active}>
        {t("save")}
      </button>
    </form>
  );
}

function Schedule({
  family,
  reload,
  refresh,
}: {
  family: Family;
  reload: () => void;
  refresh: () => Promise<void>;
}) {
  const { t } = useTranslation();
  const { run, busy } = useAction();
  const initialZone =
    family.timezone ||
    Intl.DateTimeFormat().resolvedOptions().timeZone ||
    "UTC";
  const zones: string[] =
    "supportedValuesOf" in Intl
      ? (
          Intl as unknown as { supportedValuesOf: (key: string) => string[] }
        ).supportedValuesOf("timeZone")
      : [
          initialZone,
          "UTC",
          "America/New_York",
          "Europe/London",
          "Europe/Berlin",
          "Asia/Tokyo",
          "Australia/Sydney",
        ];
  return (
    <>
      <Heading title={t("schedule")} hint={t("timezoneHint")} />
      <section className="panel">
        <form
          onSubmit={(event) => {
            const data = formData(event);
            void run(async () => {
              await api("/parent/timezone", "PUT", data);
              await refresh();
              reload();
            }, t("changed"));
          }}
        >
          <Field label={t("familyTimezone")} hint={t("timezoneRate")}>
            <select name="timezone" defaultValue={initialZone}>
              {[...new Set([initialZone, "UTC", ...zones])].map((zone) => (
                <option key={zone}>{zone}</option>
              ))}
            </select>
          </Field>
          <button disabled={busy} className="primary">
            {t("save")}
          </button>
        </form>
      </section>
      <section className="panel">
        <form
          onSubmit={(event) => {
            const data = formData(event);
            void run(async () => {
              await api("/parent/settings", "PUT", {
                daily_minutes_cap: Number(data.daily_minutes_cap),
                daily_message_cap: Number(data.daily_message_cap),
                quiet_enabled: data.quiet_enabled === "on",
                quiet_start: Number(data.quiet_start),
                quiet_end: Number(data.quiet_end),
                notify_fence: data.notify_fence === "on",
              });
              reload();
            }, t("changed"));
          }}
        >
          <div className="form-grid">
            <Field label={t("dailyMinutes")} hint={t("noLimitHint")}>
              <input
                name="daily_minutes_cap"
                type="number"
                min="0"
                max="480"
                step="1"
                required
                defaultValue={family.settings.daily_minutes_cap}
              />
            </Field>
            <Field label={t("dailyMessages")}>
              <input
                name="daily_message_cap"
                type="number"
                min="10"
                max="1000"
                step="1"
                required
                defaultValue={family.settings.daily_message_cap}
              />
            </Field>
          </div>
          <label className="check">
            <input
              name="quiet_enabled"
              type="checkbox"
              defaultChecked={family.settings.quiet_enabled}
            />
            {t("quiet")}
          </label>
          <div className="form-grid">
            {["quiet_start", "quiet_end"].map((key) => (
              <Field
                key={key}
                label={t(key === "quiet_start" ? "startHour" : "endHour")}
              >
                <select
                  name={key}
                  defaultValue={
                    family.settings[key as keyof FamilySettings] as number
                  }
                >
                  {Array.from({ length: 24 }, (_, hour) => (
                    <option key={hour} value={hour}>
                      {String(hour).padStart(2, "0")}:00
                    </option>
                  ))}
                </select>
              </Field>
            ))}
          </div>
          <p className="muted">{t("equalHours")}</p>
          <label className="check">
            <input
              type="checkbox"
              name="notify_fence"
              defaultChecked={family.settings.notify_fence}
            />
            {t("notifyFence")}
          </label>
          <p className="muted">{t("notifyHint")}</p>
          <button className="primary" disabled={busy}>
            {t("save")}
          </button>
        </form>
      </section>
    </>
  );
}

type SearchResult = {
  conversation_id: number;
  message_id: number;
  title: string;
  snippet: string;
  student_deleted: boolean;
};
function Activity({
  child,
  source,
}: {
  child?: Child;
  source: (conversation: number, message?: number) => void;
}) {
  const { t } = useTranslation();
  const [status, setStatus] = useState("all");
  const [query, setQuery] = useState("");
  const [searched, setSearched] = useState("");
  const conversations = useResource<Conversation[]>(
    child
      ? `/parent/students/${child.id}/conversations?status=${status}`
      : null,
  );
  const search = useResource<SearchResult[]>(
    child && searched
      ? `/parent/students/${child.id}/search?q=${encodeURIComponent(searched)}`
      : null,
  );
  const { run, busy } = useAction();
  if (!child) return <Empty>{t("noChildren")}</Empty>;
  return (
    <>
      <Heading
        title={t("activity")}
        hint={t("parentVisibility")}
        actions={
          <button
            disabled={busy}
            onClick={() =>
              void run(async () =>
                download(
                  await api(`/parent/students/${child.id}/export`),
                  `learning-${child.id}.json`,
                ),
              )
            }
          >
            {t("export")}
          </button>
        }
      />
      <div className="toolbar">
        <form
          className="search-form"
          onSubmit={(event) => {
            event.preventDefault();
            setSearched(query.trim());
          }}
        >
          <input
            type="search"
            minLength={2}
            placeholder={t("searchHint")}
            aria-label={t("search")}
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              if (!e.target.value) setSearched("");
            }}
          />
          <button>{t("search")}</button>
        </form>
        <select
          aria-label={t("showDeleted")}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          {["all", "active", "deleted"].map((key) => (
            <option key={key} value={key}>
              {t(key)}
            </option>
          ))}
        </select>
      </div>
      {searched ? (
        <>
          <ResourceState {...search} retry={search.reload} />
          {search.data && !search.data.length && <Empty />}
          {search.data?.map((row) => (
            <button
              className="conversation-row panel"
              key={row.message_id}
              onClick={() => source(row.conversation_id, row.message_id)}
            >
              <span>
                <strong>{row.title}</strong>
                <small>{row.snippet}</small>
                {row.student_deleted && <small>{t("deleted")}</small>}
              </span>
              <span>→</span>
            </button>
          ))}
        </>
      ) : (
        <>
          <ResourceState {...conversations} retry={conversations.reload} />
          {conversations.data && !conversations.data.length && <Empty />}
          {conversations.data?.map((row) => (
            <button
              className="conversation-row panel"
              key={row.id}
              onClick={() => source(row.id!)}
            >
              <span>
                <strong>{row.title}</strong>
                <small>
                  {contentText(row.teacher_name)} · {date(row.created_at)}
                </small>
                {row.student_deleted && (
                  <small className="badge">{t("deleted")}</small>
                )}
              </span>
              <span>→</span>
            </button>
          ))}
        </>
      )}
    </>
  );
}

type FenceEvent = {
  id: number;
  stage: string;
  decision: string;
  category: string;
  created_at: string;
  safety_education: boolean;
};
function Review({ timezone }: { timezone: string | null }) {
  const { conversationId } = useParams();
  const { t } = useTranslation();
  const messages = useResource<Message[]>(
    `/parent/conversations/${conversationId}/messages`,
  );
  const events = useResource<FenceEvent[]>(
    `/parent/conversations/${conversationId}/fence-events`,
  );
  const [reviewing, setReviewing] = useState<number | null>(null);
  const { run, busy } = useAction();
  useEffect(() => {
    if (messages.data && location.hash)
      requestAnimationFrame(() =>
        document
          .getElementById(location.hash.slice(1))
          ?.scrollIntoView({ block: "center" }),
      );
  }, [messages.data]);
  return (
    <>
      <Heading title={t("activity")} hint={t("parentVisibility")} />
      <ResourceState {...messages} retry={messages.reload} />
      <section className="transcript panel">
        {messages.data?.length === 0 && <Empty />}
        {messages.data?.map((message) => (
          <div id={`message-${message.id}`} key={message.id}>
            <small className="muted">
              {date(message.created_at, timezone)}
            </small>
            <MessageCard
              message={message}
              onReview={
                ["reject", "rewrite"].includes(message.fence_action || "")
                  ? () => setReviewing(message.id)
                  : undefined
              }
            />
          </div>
        ))}
      </section>
      <section className="panel">
        <h2>{t("boundaries")}</h2>
        <ResourceState {...events} retry={events.reload} />
        {events.data?.length === 0 && <Empty />}
        {events.data?.map((event) => (
          <article className="history-item" key={event.id}>
            <strong>
              {t(event.decision)} · {t(event.category)}
            </strong>
            <small>{date(event.created_at, timezone)}</small>
          </article>
        ))}
      </section>
      {reviewing && (
        <Dialog title={t("feedbackNote")} onClose={() => setReviewing(null)}>
          <form
            onSubmit={(event) => {
              const data = formData(event);
              void run(async () => {
                await api(
                  `/parent/conversations/${conversationId}/feedback`,
                  "POST",
                  { message_id: reviewing, note: data.note },
                );
                setReviewing(null);
              }, t("changed"));
            }}
          >
            <Field label={t("note")}>
              <textarea name="note" maxLength={500} />
            </Field>
            <button className="primary" disabled={busy}>
              {t("submit")}
            </button>
          </form>
        </Dialog>
      )}
    </>
  );
}

type Notification = {
  id: number;
  title: string;
  body: string;
  type: string;
  is_read: boolean;
  created_at: string;
  conversation_id: number | null;
  student_id?: number | null;
};
function Notifications({
  source,
  timezone,
}: {
  source: (conversation: number, student?: number) => void;
  timezone: string | null;
}) {
  const { t } = useTranslation();
  const [page, setPage] = useState(1);
  const [unread, setUnread] = useState(false);
  const [open, setOpen] = useState<Notification | null>(null);
  const resource = useResource<{
    total: number;
    unread: number;
    items: Notification[];
  }>(`/parent/notifications?page=${page}&size=20&unread_only=${unread}`);
  const { run, busy } = useAction();
  return (
    <>
      <Heading title={t("notifications")} />
      <div className="toolbar">
        <label className="check">
          <input
            type="checkbox"
            checked={unread}
            onChange={(e) => {
              setUnread(e.target.checked);
              setPage(1);
            }}
          />
          {t("unreadOnly")}
        </label>
        <button
          disabled={busy}
          onClick={() =>
            void run(async () => {
              await api("/parent/notifications/read-all", "POST");
              resource.reload();
            }, t("changed"))
          }
        >
          {t("readAll")}
        </button>
        <span>
          {t("unread")}: {resource.data?.unread || 0}
        </span>
      </div>
      <ResourceState {...resource} retry={resource.reload} />
      {resource.data && !resource.data.items.length && <Empty />}
      {resource.data?.items.map((row) => (
        <button
          className={`notification-row panel ${row.is_read ? "" : "unread"}`}
          key={row.id}
          onClick={() => {
            setOpen(row);
            if (!row.is_read)
              void run(async () => {
                await api(`/parent/notifications/${row.id}/read`, "PUT");
                resource.reload();
              });
          }}
        >
          <strong>{contentText(row.title)}</strong>
          <small>
            {date(row.created_at, timezone)} ·{" "}
            {t(row.is_read ? "read" : "unread")}
          </small>
          <p>{contentText(row.body)}</p>
        </button>
      ))}
      <div className="actions">
        <button disabled={page <= 1} onClick={() => setPage((v) => v - 1)}>
          {t("previous")}
        </button>
        <span>{page}</span>
        <button
          disabled={!resource.data || page * 20 >= resource.data.total}
          onClick={() => setPage((v) => v + 1)}
        >
          {t("more")}
        </button>
      </div>
      {open && (
        <Dialog title={contentText(open.title)} onClose={() => setOpen(null)}>
          <p className="prose">{contentText(open.body)}</p>
          <small>{date(open.created_at, timezone)}</small>
          {open.conversation_id && (
            <button
              onClick={() => {
                source(open.conversation_id!, open.student_id || undefined);
                setOpen(null);
              }}
            >
              {t("source")}
            </button>
          )}
        </Dialog>
      )}
    </>
  );
}

type SubscriptionData = {
  active: boolean;
  plan: string;
  expires_at: string;
  seat_count: number;
  used_seats: number;
  provider?: string;
  billing_source?: string;
  store?: { platform?: string };
  source?: string;
};
function Subscription({ timezone }: { timezone: string | null }) {
  const { t } = useTranslation();
  const resource = useResource<SubscriptionData>("/parent/subscription");
  return (
    <>
      <Heading title={t("subscription")} />
      <PaddleSandbox reload={resource.reload} provider={resource.data?.provider} />
      <ResourceState {...resource} retry={resource.reload} />
      {resource.data && (
        <section className="panel">
          <header className="section-heading">
            <h2>{t("access")}</h2>
            <span className="badge">
              {t(resource.data.active ? "active" : "inactive")}
            </span>
          </header>
          <dl>
            <dt>{t("expires")}</dt>
            <dd>{date(resource.data.expires_at, timezone)}</dd>
            <dt>{t("seats")}</dt>
            <dd>
              {number(resource.data.used_seats)} /{" "}
              {number(resource.data.seat_count)}
            </dd>
            <dt>{t("purchaseSource")}</dt>
            <dd>
              {resource.data.plan === "free_trial"
                ? t("freeTrial")
                : resource.data.provider === "paddle_sandbox"
                  ? "Paddle Sandbox"
                  : resource.data.provider ||
                  resource.data.billing_source ||
                  resource.data.source ||
                  resource.data.store?.platform ||
                  resource.data.plan}
            </dd>
          </dl>
          {(resource.data.provider === "googleplay" ||
            resource.data.billing_source === "googleplay" ||
            resource.data.source === "googleplay" ||
            resource.data.store?.platform === "googleplay") && (
            <a
              className="button"
              href="https://play.google.com/store/account/subscriptions"
              target="_blank"
              rel="noopener noreferrer"
            >
              {t("managePlay")}
            </a>
          )}
        </section>
      )}
    </>
  );
}
