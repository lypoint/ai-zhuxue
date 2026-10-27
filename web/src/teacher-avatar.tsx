import { useState } from "react";
import { Sparkles } from "lucide-react";
import { ROOT } from "./api";

export function TeacherAvatar({ url }: { url?: string }) {
  let src = "";
  try {
    const parsed = new URL(url || "", "https://avatar.invalid");
    if (["http:", "https:"].includes(parsed.protocol) &&
        /^\/teacher-avatars\/[a-f0-9]{32}\.(png|jpg|webp)$/.test(parsed.pathname))
      src = `${ROOT}/api${parsed.pathname}`;
  } catch { /* Invalid or unsupported avatars use the default icon. */ }
  const [failed, setFailed] = useState("");
  return src && failed !== src ? (
    <img className="teacher-avatar" src={src} alt="" aria-hidden="true"
      width={32} height={32} referrerPolicy="no-referrer" onError={() => setFailed(src)} />
  ) : (
    <Sparkles className="teacher-avatar teacher-avatar-placeholder" aria-hidden="true" />
  );
}
