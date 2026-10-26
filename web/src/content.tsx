import { useMemo, useState, type ImgHTMLAttributes } from "react";
import { useTranslation } from "react-i18next";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import {
  Bookmark,
  Copy,
  Flag,
  ImagePlus,
  ThumbsUp,
  ThumbsDown,
  MessageCircle,
} from "lucide-react";
import {
  ROOT,
  ROLE,
  type Message,
  type ImageBlock,
  type Favorite,
} from "./api";
import {
  copy,
  Dialog,
  Empty,
  ResourceState,
  useAction,
  useResource,
} from "./ui";
import { date, tx, contentText } from "./i18n";
import { normalizeMathMarkdown } from "./math-markdown";

export function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        skipHtml
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { strict: false, trust: false }]]}
        components={{
          a: ({ children }) => <span>{children}</span>,
          img: () => null,
        }}
      >
        {normalizeMathMarkdown(children)}
      </ReactMarkdown>
    </div>
  );
}
// Some browsers omit Server-Timing for image elements; a request nonce also permits pairing.
function PerformanceImage(props: ImgHTMLAttributes<HTMLImageElement>) {
  const id = useMemo(() => {
    try { return ROLE === "student" ? crypto.randomUUID() : ""; } catch { return ""; }
  }, [props.src]);
  const src = props.src && id ? `${props.src}${props.src.includes("?") ? "&" : "?"}_trace=${id}` : props.src;
  return <img {...props} src={src} />;
}

export function Images({ blocks }: { blocks?: ImageBlock[] }) {
  const [open, setOpen] = useState<ImageBlock | null>(null);
  const [failed, setFailed] = useState<Record<string, boolean>>({});
  const [version, setVersion] = useState(0);
  const { t } = useTranslation();
  const images = (blocks || []).filter(
    (b) => b.type === "image" && /^[a-f0-9]{32}$/.test(b.asset_id || ""),
  );
  return (
    <>
      {images.length > 0 && (
        <div className="message-images">
          {images.map((block) => (
            <figure key={block.asset_id}>
              {failed[block.asset_id!] ? (
                <button
                  onClick={() => {
                    setFailed((v) => ({ ...v, [block.asset_id!]: false }));
                    setVersion((v) => v + 1);
                  }}
                >
                  {t("imageUnavailable")} · {t("retry")}
                </button>
              ) : (
                <button
                  className="image-button"
                  onClick={() => setOpen(block)}
                  aria-label={t("viewImage")}
                >
                  <PerformanceImage
                    src={`${ROOT}/media/${block.asset_id}?v=${version}`}
                    alt={
                      block.caption
                        ? contentText(block.caption)
                        : t("viewImage")
                    }
                    loading="lazy"
                    onError={() =>
                      setFailed((v) => ({ ...v, [block.asset_id!]: true }))
                    }
                  />
                </button>
              )}
              {block.caption && (
                <figcaption>{contentText(block.caption)}</figcaption>
              )}
            </figure>
          ))}
        </div>
      )}
      {open && (
        <Dialog title={t("viewImage")} onClose={() => setOpen(null)}>
          <PerformanceImage
            className="full-image"
            src={`${ROOT}/media/${open.asset_id}`}
            alt={open.caption ? contentText(open.caption) : t("viewImage")}
          />
          {open.caption && <p>{contentText(open.caption)}</p>}
        </Dialog>
      )}
    </>
  );
}
export function MessageCard({
  message,
  teacher,
  feedback,
  saved,
  onFeedback,
  onSave,
  onReport,
  onDiagram,
  onReview,
  busy = false,
}: {
  message: Message;
  teacher?: string;
  feedback?: string;
  saved?: boolean;
  onFeedback?: (action: string) => void;
  onSave?: () => void;
  onReport?: () => void;
  onDiagram?: () => void;
  onReview?: () => void;
  busy?: boolean;
}) {
  const { t } = useTranslation();
  const action = useAction();
  const assistant = message.role === "assistant";
  const eligible =
    assistant &&
    ["allow", "rewrite", ""].includes(message.fence_action || "") &&
    message.content.trim();
  return (
    <article
      className={`message ${assistant ? "assistant" : "user"}`}
      data-message-id={message.id}
    >
      <div className="message-byline">
        {assistant
          ? teacher
            ? contentText(teacher)
            : t("teacher")
          : t(ROLE === "student" ? "you" : "student")}
        {message.fence_action === "failed" && (
          <span className="badge error">{t("retry")}</span>
        )}
      </div>
      <Markdown>{message.content}</Markdown>
      <Images blocks={message.content_blocks} />
      {message.id > 0 && (
        <div className="message-actions">
          <button
            className="icon-button"
            aria-label={t("copy")}
            onClick={() =>
              void action.run(() => copy(message.content), t("copied"))
            }
          >
            <Copy size={17} />
          </button>
          {onSave && (
            <button
              className={`icon-button ${saved ? "selected" : ""}`}
              aria-label={t(saved ? "removeSaved" : "bookmark")}
              onClick={onSave}
              disabled={busy}
            >
              <Bookmark size={17} fill={saved ? "currentColor" : "none"} />
            </button>
          )}
          {onReport && (
            <button
              className="icon-button"
              aria-label={t("report")}
              onClick={onReport}
            >
              <Flag size={17} />
            </button>
          )}
          {onReview && <button onClick={onReview}>{t("flagged")}</button>}
          {onDiagram && eligible && (
            <button onClick={onDiagram} disabled={busy}>
              <ImagePlus size={17} />
              {t("diagram")}
            </button>
          )}
        </div>
      )}
      {eligible && onFeedback && (
        <div className="feedback-actions" aria-label={t("feedback")}>
          {[
            ["understood", ThumbsUp],
            ["not_understood", ThumbsDown],
            ["continue", MessageCircle],
          ].map(([key, Icon]) => {
            const id = key as string;
            const FeedbackIcon = Icon as typeof ThumbsUp;
            return (
              <button
                key={id}
                className={feedback === id ? "selected" : ""}
                aria-pressed={feedback === id}
                disabled={busy}
                onClick={() => onFeedback(id)}
              >
                <FeedbackIcon size={16} />
                {t(id)}
              </button>
            );
          })}
        </div>
      )}
      {message.image_job &&
        ["queued", "running"].includes(message.image_job.state) && (
          <p className="muted" role="status">
            {t("pendingImage")}
          </p>
        )}
      {message.image_job &&
        ["failed", "skipped"].includes(message.image_job.state) && (
          <p className="muted">
            {tx(message.image_job.error || t("imageUnavailable"))}
          </p>
        )}
    </article>
  );
}
export function Favorites({
  path,
  onSource,
}: {
  path: string;
  onSource: (conversation: number, message?: number | null) => void;
}) {
  const { t } = useTranslation();
  const resource = useResource<Favorite[]>(path);
  const { run, busy } = useAction();
  const [search, setSearch] = useState("");
  const rows = (resource.data || []).filter((row) =>
    row.content.toLowerCase().includes(search.toLowerCase()),
  );
  return (
    <>
      <div className="toolbar">
        <input
          type="search"
          placeholder={t("search")}
          aria-label={t("search")}
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>
      <ResourceState {...resource} retry={resource.reload} />
      {resource.data && !rows.length && <Empty />}
      {rows.map((row) => (
        <section className="panel" key={row.id}>
          <small className="muted">{date(row.created_at)}</small>
          <Markdown>{row.content}</Markdown>
          <Images blocks={row.content_blocks} />
          <div className="actions">
            {row.conversation_id ? (
              <button
                onClick={() => onSource(row.conversation_id!, row.message_id)}
              >
                {t("source")}
              </button>
            ) : (
              <small>{t("sourceUnavailable")}</small>
            )}
            {ROLE === "student" && (
              <button
                disabled={busy}
                onClick={() =>
                  void run(async () => {
                    const { api } = await import("./api");
                    await api(`/chat/favorites/${row.id}`, "DELETE");
                    resource.reload();
                  }, t("changed"))
                }
              >
                {t("removeSaved")}
              </button>
            )}
          </div>
        </section>
      ))}
    </>
  );
}
