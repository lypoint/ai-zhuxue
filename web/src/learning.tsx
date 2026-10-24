import { useRef } from "react";
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
import { date, number } from "./i18n";

type Learning = {
  balance: number;
  earned: number;
  spent: number;
  today: { stars: number; date: string };
  days: {
    date: string;
    counts: Record<string, number>;
    total: number;
    stars: number;
  }[];
  agreements: {
    id: number;
    reward: string;
    stars: number;
    fulfillment: string;
    accepted: boolean;
  }[];
  redemptions: {
    id: number;
    reward: string;
    stars: number;
    fulfillment: string;
    fulfilled: boolean;
    created_at: string;
  }[];
};
export default function Learning({ prefix }: { prefix: string }) {
  const { t } = useTranslation();
  const resource = useResource<Learning>(`${prefix}/learning`);
  const { busy, run } = useAction();
  const proposeId = useRef(crypto.randomUUID());
  const redeemIds = useRef<Record<number, string>>({});
  const data = resource.data;
  return (
    <>
      <ResourceState {...resource} retry={resource.reload} />
      {data && (
        <>
          <div className="metrics">
            <section>
              <span>{t("balance")}</span>
              <strong>{number(data.balance)}</strong>
            </section>
            <section>
              <span>{t("earned")}</span>
              <strong>{number(data.earned)}</strong>
            </section>
            <section>
              <span>{t("spent")}</span>
              <strong>{number(data.spent)}</strong>
            </section>
          </div>
          <p className="notice">{t("rewardRule")}</p>
          <section className="panel">
            <h2>{t("agreements")}</h2>
            {!data.agreements.length && <Empty />}
            {data.agreements.map((row) => (
              <article className="reward-row" key={row.id}>
                <div>
                  <h3>{row.reward}</h3>
                  <p>
                    {number(row.stars)} ★ · {row.fulfillment}
                  </p>
                  <small>
                    {row.accepted ? t("accept") + " ✓" : t("awaiting")}
                  </small>
                </div>
                <div className="actions">
                  {ROLE === "student" && !row.accepted && (
                    <button
                      disabled={busy}
                      onClick={() =>
                        void run(async () => {
                          await api(
                            `/chat/reward-agreements/${row.id}/accept`,
                            "POST",
                          );
                          resource.reload();
                        }, t("changed"))
                      }
                    >
                      {t("accept")}
                    </button>
                  )}
                  {row.accepted && (
                    <button
                      disabled={busy || data.balance < row.stars}
                      onClick={() =>
                        void run(async () => {
                          const requestId = (redeemIds.current[row.id] ||=
                            crypto.randomUUID());
                          await api(`${prefix}/redemptions`, "POST", {
                            agreement_id: row.id,
                            request_id: requestId,
                          });
                          delete redeemIds.current[row.id];
                          resource.reload();
                        }, t("changed"))
                      }
                    >
                      {t("redeem")}
                    </button>
                  )}
                </div>
              </article>
            ))}
          </section>
          {ROLE === "parent" && (
            <section className="panel">
              <h2>{t("propose")}</h2>
              <form
                onSubmit={(event) => {
                  const data = formData(event);
                  const form = event.currentTarget;
                  void run(async () => {
                    await api(`${prefix}/reward-agreements`, "POST", {
                      ...data,
                      stars: Number(data.stars),
                      request_id: proposeId.current,
                    });
                    proposeId.current = crypto.randomUUID();
                    form.reset();
                    resource.reload();
                  }, t("changed"));
                }}
              >
                <div className="form-grid">
                  <Field label={t("reward")}>
                    <input name="reward" required maxLength={200} />
                  </Field>
                  <Field label={t("stars")}>
                    <input
                      name="stars"
                      type="number"
                      min="1"
                      max="100000"
                      required
                      step="1"
                    />
                  </Field>
                  <Field label={t("fulfillment")}>
                    <input name="fulfillment" required maxLength={100} />
                  </Field>
                </div>
                <button className="primary" disabled={busy}>
                  {t("propose")}
                </button>
              </form>
            </section>
          )}
          <section className="panel">
            <h2>{t("redemptions")}</h2>
            {!data.redemptions.length && <Empty />}
            {data.redemptions.map((row) => (
              <article className="reward-row" key={row.id}>
                <div>
                  <h3>{row.reward}</h3>
                  <p>
                    {number(row.stars)} ★ · {row.fulfillment}
                  </p>
                  <small>{date(row.created_at)}</small>
                </div>
                {row.fulfilled ? (
                  <span className="badge">{t("fulfilled")}</span>
                ) : ROLE === "parent" ? (
                  <button
                    disabled={busy}
                    onClick={() =>
                      void run(async () => {
                        await api(
                          `${prefix}/redemptions/${row.id}/fulfill`,
                          "POST",
                        );
                        resource.reload();
                      }, t("changed"))
                    }
                  >
                    {t("fulfill")}
                  </button>
                ) : (
                  <span className="badge">{t("fulfillment")}</span>
                )}
              </article>
            ))}
          </section>
          <section className="panel">
            <h2>{t("feedbackHistory")}</h2>
            {!data.days.length && <Empty />}
            {data.days.map((day) => (
              <article className="feedback-day" key={day.date}>
                <strong>{date(day.date)}</strong>
                <span>
                  {Object.entries(day.counts)
                    .map(([key, value]) => `${t(key)}: ${number(value)}`)
                    .join(" · ")}
                </span>
                <span>{day.stars} ★</span>
              </article>
            ))}
          </section>
        </>
      )}
    </>
  );
}
