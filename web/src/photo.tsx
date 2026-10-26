import { startPerformance } from "./request-performance";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { Camera, ImagePlus, X } from "lucide-react";
import { browser, request, sendPerformance, ROLE, type ImageBlock } from "./api";
import { Dialog, Field, useAction, useNotify } from "./ui";

export type Attachment = {
  key: string;
  blob: Blob;
  preview: string;
  status: "uploading" | "ready" | "failed";
  asset?: ImageBlock;
};
export function PhotoPicker({
  attachments,
  setAttachments,
  conversation,
  teacher,
  disabled,
}: {
  attachments: Attachment[];
  setAttachments: React.Dispatch<React.SetStateAction<Attachment[]>>;
  conversation: number | null;
  teacher: number | null;
  disabled: boolean;
}) {
  const { t } = useTranslation();
  const notify = useNotify();
  const fileRef = useRef<HTMLInputElement>(null);
  const cameraRef = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const upload = async (attachment: Attachment) => {
    setAttachments((rows) =>
      rows.map((row) =>
        row.key === attachment.key ? { ...row, status: "uploading" } : row,
      ),
    );
    const query = new URLSearchParams();
    if (conversation) query.set("conversation_id", String(conversation));
    if (teacher !== null) query.set("teacher_id", String(teacher));
    const timing = ROLE === "student" ? startPerformance("image_upload", sendPerformance) : undefined;
    try {
      const response = await request("/upload?" + query, {
        method: "POST",
        body: attachment.blob,
        headers: { "Content-Type": "application/octet-stream" },
      }, timing);
      const asset = (await response.json()) as ImageBlock;
      if (timing) timing.result = "success";
      timing?.mark("browser_done_ms");
      setAttachments((rows) =>
        rows.map((row) =>
          row.key === attachment.key ? { ...row, status: "ready", asset } : row,
        ),
      );
    } catch (error) {
      if (timing) timing.result = "error";
      setAttachments((rows) =>
        rows.map((row) =>
          row.key === attachment.key ? { ...row, status: "failed" } : row,
        ),
      );
      notify(error instanceof Error ? error.message : t("uploadFailed"), true);
    } finally { timing?.finish(); }
  };
  const select = (files: FileList | null) => {
    const selected = files?.[0];
    if (!selected) return;
    if (attachments.length >= 3) {
      notify(t("imageLimit"), true);
      return;
    }
    if (!["image/jpeg", "image/png", "image/webp"].includes(selected.type)) {
      notify(t("imageType"), true);
      return;
    }
    if (selected.size > 30 * 1024 * 1024) {
      notify(t("fileTooLarge"), true);
      return;
    }
    setFile(selected);
  };
  return (
    <div className="photo-picker">
      <div className="attachment-row">
        {attachments.map((row) => (
          <div className="attachment" key={row.key}>
            <img src={row.preview} alt={t("addPhoto")} />
            <span>
              {t(
                row.status === "uploading"
                  ? "uploading"
                  : row.status === "failed"
                    ? "uploadFailed"
                    : "saved",
              )}
            </span>
            {row.status === "failed" && (
              <button
                type="button"
                disabled={disabled}
                onClick={() => void upload(row)}
              >
                {t("retry")}
              </button>
            )}
            <button
              className="icon-button"
              type="button"
              disabled={disabled}
              aria-label={t("remove")}
              onClick={() => {
                URL.revokeObjectURL(row.preview);
                setAttachments((rows) =>
                  rows.filter((item) => item.key !== row.key),
                );
              }}
            >
              <X size={16} />
            </button>
          </div>
        ))}
      </div>
      <div className="photo-buttons">
        <input
          className="sr-only"
          ref={fileRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(event) => {
            select(event.target.files);
            event.target.value = "";
          }}
        />
        <input
          className="sr-only"
          ref={cameraRef}
          type="file"
          accept="image/jpeg,image/png,image/webp"
          capture="environment"
          onChange={(event) => {
            select(event.target.files);
            event.target.value = "";
          }}
        />
        <button
          type="button"
          disabled={disabled || attachments.length >= 3}
          onClick={() => fileRef.current?.click()}
        >
          <ImagePlus size={18} />
          {t("addPhoto")}
        </button>
        <button
          type="button"
          className="icon-button"
          disabled={disabled || attachments.length >= 3}
          aria-label={t("camera")}
          onClick={() => cameraRef.current?.click()}
        >
          <Camera size={19} />
        </button>
      </div>
      {file && (
        <Crop
          file={file}
          onClose={() => setFile(null)}
          onDone={(blob) => {
            const attachment: Attachment = {
              key: crypto.randomUUID(),
              blob,
              preview: URL.createObjectURL(blob),
              status: "uploading",
            };
            setAttachments((rows) => [...rows, attachment]);
            setFile(null);
            void upload(attachment);
          }}
        />
      )}
    </div>
  );
}
function Crop({
  file,
  onClose,
  onDone,
}: {
  file: File;
  onClose: () => void;
  onDone: (blob: Blob) => void;
}) {
  const { t } = useTranslation();
  const [url, setUrl] = useState(() => URL.createObjectURL(file));
  const image = useRef<HTMLImageElement>(null);
  const [crop, setCrop] = useState({
    left: 0,
    top: 0,
    width: 100,
    height: 100,
  });
  const { busy, run } = useAction();
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  useEffect(() => () => URL.revokeObjectURL(url), [url]);
  return (
    <Dialog title={t("crop")} onClose={onClose}>
      <p>{t("cropHint")}</p>
      <div className="crop-preview">
        <img
          ref={image}
          src={url}
          alt={t("crop")}
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
        <div
          className="crop-selection"
          style={{
            left: crop.left + "%",
            top: crop.top + "%",
            width: crop.width + "%",
            height: crop.height + "%",
          }}
        />
      </div>
      {failed && (
        <p role="alert" className="notice error">
          {t("imageType")}
        </p>
      )}
      <div className="form-grid">
        {(["left", "top", "width", "height"] as const).map((key) => (
          <Field
            key={key}
            label={t(
              {
                left: "cropLeft",
                top: "cropTop",
                width: "cropWidth",
                height: "cropHeight",
              }[key],
            )}
          >
            <input
              type="range"
              min={key === "width" || key === "height" ? 5 : 0}
              max={
                key === "width"
                  ? 100 - crop.left
                  : key === "height"
                    ? 100 - crop.top
                    : 95
              }
              value={crop[key]}
              onChange={(event) => {
                const next = { ...crop, [key]: Number(event.target.value) };
                next.width = Math.min(next.width, 100 - next.left);
                next.height = Math.min(next.height, 100 - next.top);
                setCrop(next);
              }}
            />
          </Field>
        ))}
      </div>
      <div className="actions">
        <button
          type="button"
          disabled={busy || !loaded}
          onClick={() =>
            void run(async () => {
              const source = image.current!;
              const scale = Math.min(
                1,
                2048 / Math.max(source.naturalWidth, source.naturalHeight),
              );
              const canvas = document.createElement("canvas");
              canvas.width = Math.max(
                1,
                Math.round(source.naturalHeight * scale),
              );
              canvas.height = Math.max(
                1,
                Math.round(source.naturalWidth * scale),
              );
              const context = canvas.getContext("2d");
              if (!context)
                throw new Error("Could not crop the image. Please try again.");
              context.fillStyle = "#fff";
              context.fillRect(0, 0, canvas.width, canvas.height);
              context.translate(canvas.width, 0);
              context.rotate(Math.PI / 2);
              context.drawImage(source, 0, 0, canvas.height, canvas.width);
              const rotated = await new Promise<Blob>((resolve, reject) =>
                canvas.toBlob(
                  (value) =>
                    value
                      ? resolve(value)
                      : reject(
                          new Error(
                            "Could not crop the image. Please try again.",
                          ),
                        ),
                  "image/png",
                ),
              );
              setLoaded(false);
              setCrop({ left: 0, top: 0, width: 100, height: 100 });
              setUrl(URL.createObjectURL(rotated));
            })
          }
        >
          {t("rotatePhoto")}
        </button>
        <button
          type="button"
          className="primary"
          disabled={busy || !loaded}
          onClick={() =>
            void run(async () => {
              const source = image.current!;
              const sourceWidth = Math.max(
                  1,
                  (source.naturalWidth * crop.width) / 100,
                ),
                sourceHeight = Math.max(
                  1,
                  (source.naturalHeight * crop.height) / 100,
                );
              const scale = Math.min(
                1,
                2048 / Math.max(sourceWidth, sourceHeight),
              );
              const canvas = document.createElement("canvas");
              canvas.width = Math.max(1, Math.round(sourceWidth * scale));
              canvas.height = Math.max(1, Math.round(sourceHeight * scale));
              const context = canvas.getContext("2d");
              if (!context)
                throw new Error("Could not crop the image. Please try again.");
              context.fillStyle = "#fff";
              context.fillRect(0, 0, canvas.width, canvas.height);
              context.drawImage(
                source,
                (source.naturalWidth * crop.left) / 100,
                (source.naturalHeight * crop.top) / 100,
                sourceWidth,
                sourceHeight,
                0,
                0,
                canvas.width,
                canvas.height,
              );
              const blob = await new Promise<Blob>((resolve, reject) =>
                canvas.toBlob(
                  (value) =>
                    value
                      ? resolve(value)
                      : reject(
                          new Error(
                            "Could not crop the image. Please try again.",
                          ),
                        ),
                  "image/jpeg",
                  0.88,
                ),
              );
              onDone(blob);
            })
          }
        >
          {t("applyCrop")}
        </button>
      </div>
    </Dialog>
  );
}
