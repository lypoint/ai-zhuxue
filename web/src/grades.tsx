import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, type Grade } from "./api";
import {
  Confirm,
  Dialog,
  Empty,
  Field,
  formData,
  ResourceState,
  useAction,
  useResource,
} from "./ui";
import { date, number } from "./i18n";

type Version = Grade & {
  version: number;
  edited_by_role: string;
  reason: string;
  created_at: string;
};
type Trend = {
  points: {
    id: number;
    exam_date: string;
    score: number;
    max_score: number;
    percentage: number;
  }[];
  direction: string;
  delta: number | null;
};
export default function Grades({
  prefix,
  timezone,
}: {
  prefix: string;
  timezone?: string | null;
}) {
  const { t } = useTranslation();
  const [deleted, setDeleted] = useState(false);
  const resource = useResource<Grade[]>(
    `${prefix}/grades?include_deleted=${deleted}`,
  );
  const { run, busy } = useAction();
  const [editing, setEditing] = useState<Grade | "new" | null>(null);
  const [removing, setRemoving] = useState<Grade | null>(null);
  const [version, setVersion] = useState<number | null>(null);
  const [subject, setSubject] = useState("");
  const trend = useResource<Trend>(
    subject
      ? `${prefix}/grade-trend?subject=${encodeURIComponent(subject)}`
      : null,
  );
  const history = useResource<Version[]>(
    version ? `${prefix}/grades/${version}/history` : null,
  );
  const rows = resource.data || [];
  const subjects = [
    ...new Set(rows.filter((row) => !row.deleted).map((row) => row.subject)),
  ];
  return (
    <>
      <div className="toolbar">
        <button className="primary" onClick={() => setEditing("new")}>
          {t("addGrade")}
        </button>
        <label className="check">
          <input
            type="checkbox"
            checked={deleted}
            onChange={(e) => setDeleted(e.target.checked)}
          />
          {t("showDeleted")}
        </label>
      </div>
      <ResourceState {...resource} retry={resource.reload} />
      {resource.data && !rows.length && <Empty />}
      {rows.map((row) => (
        <article
          className={`panel grade-row ${row.deleted ? "removed" : ""}`}
          key={row.id}
        >
          <div>
            <span className="eyebrow">
              {row.subject} · {date(row.exam_date)}
            </span>
            <h3>{row.title || t(row.grade_type)}</h3>
            <p>{row.term}</p>
            {row.note && <p className="muted">{row.note}</p>}
          </div>
          <strong className="grade-value">
            {number(row.score)} <small>/ {number(row.max_score)}</small>
          </strong>
          <div className="actions">
            {row.deleted ? (
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    await api(`${prefix}/grades/${row.id}/restore`, "POST");
                    resource.reload();
                  }, t("changed"))
                }
              >
                {t("restore")}
              </button>
            ) : (
              <>
                <button onClick={() => setEditing(row)}>{t("edit")}</button>
                <button onClick={() => setRemoving(row)}>{t("remove")}</button>
              </>
            )}
            <button onClick={() => setVersion(row.id)}>{t("history")}</button>
          </div>
        </article>
      ))}
      <section className="panel">
        <h2>{t("trend")}</h2>
        <p className="muted">{t("trendHint")}</p>
        <Field label={t("subject")}>
          <select value={subject} onChange={(e) => setSubject(e.target.value)}>
            <option value="">—</option>
            {subjects.map((item) => (
              <option key={item}>{item}</option>
            ))}
          </select>
        </Field>
        {subject && <ResourceState {...trend} retry={trend.reload} />}
        {trend.data && (
          <div className="bar-chart" role="img" aria-label={t("trend")}>
            {trend.data.points.map((point) => (
              <div className="bar-item" key={point.id}>
                <strong>
                  {number(point.score)}/{number(point.max_score)}
                </strong>
                <div className="bar-track">
                  <div style={{ height: `${point.percentage}%` }} />
                </div>
                <small>{date(point.exam_date)}</small>
              </div>
            ))}
          </div>
        )}
      </section>
      {editing && (
        <Dialog
          title={t(editing === "new" ? "addGrade" : "edit")}
          onClose={() => setEditing(null)}
        >
          <form
            onSubmit={(event) => {
              const data = formData(event);
              void run(async () => {
                const payload = {
                  ...data,
                  score: Number(data.score),
                  max_score: Number(data.max_score),
                };
                if (payload.score > payload.max_score)
                  throw new Error("Score cannot exceed the maximum");
                await api(
                  `${prefix}/grades${editing === "new" ? "" : "/" + editing.id}`,
                  editing === "new" ? "POST" : "PATCH",
                  payload,
                );
                setEditing(null);
                resource.reload();
                trend.reload();
              }, t("changed"));
            }}
          >
            <div className="form-grid">
              {[
                "subject",
                "title",
                "exam_date",
                "term",
                "score",
                "max_score",
              ].map((key) => {
                const value =
                  editing === "new"
                    ? ""
                    : String(editing[key as keyof Grade] ?? "");
                const numeric = key === "score" || key === "max_score";
                return (
                  <Field
                    key={key}
                    label={t(
                      (
                        {
                          exam_date: "examDate",
                          max_score: "maxScore",
                        } as Record<string, string>
                      )[key] || key,
                    )}
                  >
                    <input
                      name={key}
                      type={
                        numeric
                          ? "number"
                          : key === "exam_date"
                            ? "date"
                            : "text"
                      }
                      min={
                        key === "max_score" ? "0.01" : numeric ? 0 : undefined
                      }
                      step={numeric ? "any" : undefined}
                      required={[
                        "subject",
                        "exam_date",
                        "score",
                        "max_score",
                      ].includes(key)}
                      defaultValue={value}
                      maxLength={key === "subject" ? 40 : 100}
                    />
                  </Field>
                );
              })}
              <Field label={t("gradeType")}>
                <select
                  name="grade_type"
                  defaultValue={editing === "new" ? "exam" : editing.grade_type}
                >
                  {["exam", "homework", "quiz", "other"].map((type) => (
                    <option key={type} value={type}>
                      {t(type)}
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <Field label={t("note")}>
              <textarea
                name="note"
                defaultValue={editing === "new" ? "" : editing.note}
                maxLength={2000}
              />
            </Field>
            <Field label={t("reason")}>
              <input name="reason" maxLength={200} />
            </Field>
            <button className="primary" disabled={busy}>
              {t("save")}
            </button>
          </form>
        </Dialog>
      )}
      {removing && (
        <Confirm
          title={t("remove")}
          hint={t("deleteGrade")}
          onClose={() => setRemoving(null)}
          action={async () => {
            await api(`${prefix}/grades/${removing.id}`, "DELETE");
            resource.reload();
            trend.reload();
          }}
        />
      )}
      {version && (
        <Dialog title={t("history")} onClose={() => setVersion(null)}>
          <ResourceState {...history} retry={history.reload} />
          {history.data?.map((row) => (
            <section className="history-item" key={row.version}>
              <h3>
                {t("version")} {row.version} · {row.subject}
              </h3>
              <p>
                {row.title} · {number(row.score)} / {number(row.max_score)}
              </p>
              <p>
                {date(row.exam_date)} · {t(row.grade_type)} · {row.term}
              </p>
              <p>{row.note}</p>
              <small>
                {row.reason === "deleted"
                  ? t("gradeDeleted")
                  : row.reason === "restored"
                    ? t("restored")
                    : row.reason}{" "}
                · {date(row.created_at, timezone)} · {t(row.edited_by_role)}
              </small>
            </section>
          ))}
        </Dialog>
      )}
    </>
  );
}
