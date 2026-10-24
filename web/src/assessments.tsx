import { useState } from "react";
import { useTranslation } from "react-i18next";
import { api, ROLE } from "./api";
import {
  Empty,
  Field,
  formData,
  ResourceState,
  useAction,
  useResource,
} from "./ui";
import { date, number, tx } from "./i18n";

type Assessment = {
  assessment_id: number;
  status: string;
  period: { from: string; to: string };
  question_count?: number;
  assistant_message_count?: number;
  subjects?: {
    subject: string;
    question_count: number;
    evidence_conversation_ids: number[];
  }[];
  mastery_signals?: string[];
  needs_practice?: string[];
  recommendations?: string[];
  signals?: {
    type: string;
    level: string;
    confidence: number;
    evidence: {
      message_id: number;
      conversation_id: number;
      excerpt: string;
      created_at: string;
    }[];
  }[];
  ack_status?: string;
  model: string;
};
export default function Assessments({
  prefix,
  timezone,
  onSource,
}: {
  prefix: string;
  timezone?: string | null;
  onSource: (conversation: number, message?: number) => void;
}) {
  const { t } = useTranslation();
  const [type, setType] = useState("academic");
  const resource = useResource<Assessment[]>(`${prefix}/${type}-assessments`);
  const { run, busy } = useAction();
  const today = new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone || "UTC",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
  const month = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10);
  return (
    <>
      <p className="notice">{t("assessmentHint")}</p>
      {ROLE === "parent" && (
        <div className="tabs">
          <button
            className={type === "academic" ? "selected" : ""}
            onClick={() => setType("academic")}
          >
            {t("academic")}
          </button>
          <button
            className={type === "wellbeing" ? "selected" : ""}
            onClick={() => setType("wellbeing")}
          >
            {t("wellbeing")}
          </button>
        </div>
      )}
      <form
        className="panel"
        onSubmit={(event) => {
          const data = formData(event);
          void run(async () => {
            await api(`${prefix}/${type}-assessments`, "POST", data);
            resource.reload();
          }, t("changed"));
        }}
      >
        <div className="toolbar">
          <Field label={t("from")}>
            <input
              type="date"
              name="from"
              defaultValue={month}
              required
              max={today}
            />
          </Field>
          <Field label={t("to")}>
            <input
              type="date"
              name="to"
              defaultValue={today}
              required
              max={today}
            />
          </Field>
          <button className="primary" disabled={busy}>
            {t("generate")}
          </button>
        </div>
      </form>
      <ResourceState {...resource} retry={resource.reload} />
      {resource.data && !resource.data.length && <Empty />}
      {resource.data?.map((row) => (
        <article
          className="panel"
          key={row.assessment_id}
          data-assessment-id={row.assessment_id}
        >
          <header className="section-heading">
            <h2>
              {date(row.period.from)} – {date(row.period.to)}
            </h2>
            <small>{t("basedOnRecords")}</small>
          </header>
          {row.question_count !== undefined && (
            <p>
              {t("questions")}: {number(row.question_count)}
            </p>
          )}
          {row.subjects?.map((subject) => (
            <section className="history-item" key={subject.subject}>
              <h3>
                {tx(subject.subject)} · {number(subject.question_count)}
              </h3>
              <div className="actions">
                {subject.evidence_conversation_ids.map((id) => (
                  <button key={id} onClick={() => onSource(id)}>
                    {t("source")} #{id}
                  </button>
                ))}
              </div>
            </section>
          ))}
          {row.mastery_signals && row.mastery_signals.length > 0 && (
            <p>
              {t("understood")}: {row.mastery_signals.join(", ")}
            </p>
          )}
          {row.needs_practice && row.needs_practice.length > 0 && (
            <p>
              {t("not_understood")}: {row.needs_practice.join(", ")}
            </p>
          )}
          {row.signals?.map((signal) => (
            <section
              key={signal.type}
              className={`notice ${signal.level === "urgent" ? "error" : ""}`}
            >
              <h3>
                {t(signal.type)} · {t(signal.level)}
              </h3>
              <p>{t("evidence")}</p>
              {signal.evidence.map((item) => (
                <blockquote key={item.message_id}>
                  <p>{item.excerpt}</p>
                  <small>{date(item.created_at, timezone)}</small>
                  <button
                    onClick={() =>
                      onSource(item.conversation_id, item.message_id)
                    }
                  >
                    {t("source")}
                  </button>
                </blockquote>
              ))}
            </section>
          ))}
          {row.signals?.length === 0 && <p>{t("noResults")}</p>}
          {!!row.recommendations?.length && (
            <section className="history-item">
              <h3>{t("suggestions")}</h3>
              <ul>
                {row.recommendations.map((suggestion, index) => (
                  <li key={index}>{tx(suggestion)}</li>
                ))}
              </ul>
            </section>
          )}
          {type === "wellbeing" && (
            <div className="actions">
              <span className="badge">
                {row.ack_status === "pending"
                  ? t("awaiting")
                  : t(row.ack_status || "awaiting")}
              </span>
              {["acknowledged", "not_needed"].map((status) => (
                <button
                  key={status}
                  disabled={busy}
                  onClick={() =>
                    void run(async () => {
                      await api(
                        `/parent/wellbeing-assessments/${row.assessment_id}/ack`,
                        "POST",
                        { status },
                      );
                      resource.reload();
                    }, t("changed"))
                  }
                >
                  {t(status === "acknowledged" ? "acknowledge" : "notNeeded")}
                </button>
              ))}
            </div>
          )}
          <small className="muted">{t("assessmentHint")}</small>
        </article>
      ))}
    </>
  );
}
