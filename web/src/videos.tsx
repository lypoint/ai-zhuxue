import { useEffect, useRef, useState } from "react";
import { api, request } from "./api";
import { Heading } from "./ui";
import { tx } from "./i18n";

type Lesson = { id: string; title: string; author: string; duration: string };
type Results = { items: Lesson[]; page: number; has_more: boolean };
type Playback = { id: string; title: string; embed_url: string };

export default function Videos() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Results | null>(null);
  const [searched, setSearched] = useState("");
  const [playing, setPlaying] = useState<Playback | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const current = useRef(0);
  useEffect(() => () => { current.current++; }, []);
  useEffect(() => {
    if (!playing) return;
    let since = performance.now();
    let active = !document.hidden;
    let checking = false;
    let disposed = false;
    const pulse = async () => {
      if (checking || !active) return;
      checking = true;
      const seconds = Math.min(90, Math.floor((performance.now() - since) / 1000));
      since = performance.now();
      try {
        await request("/heartbeat", { method: "POST", body: JSON.stringify({ seconds }), keepalive: true });
        const status = await api<{ resting: boolean; remaining_seconds: number | null }>("/chat/availability");
        if (!disposed && (status.resting || status.remaining_seconds === 0)) {
          setPlaying(null);
          setError(tx("视频学习已暂停，请休息后再来"));
        }
      } catch (e) {
        if (disposed) return;
        setPlaying(null);
        setError(e instanceof Error ? tx(e.message) : tx("视频加载失败，请重试"));
      } finally { checking = false; }
    };
    void pulse();
    const timer = setInterval(() => void pulse(), 15000);
    const hide = () => {
      if (document.hidden) {
        void pulse();
        active = false;
        // Unmount the cross-origin player to stop audio when the page is hidden.
        setPlaying(null);
      }
    };
    document.addEventListener("visibilitychange", hide);
    return () => {
      disposed = true;
      clearInterval(timer);
      document.removeEventListener("visibilitychange", hide);
      if (active) void request("/heartbeat", { method: "POST", body: JSON.stringify({ seconds: Math.min(90, Math.floor((performance.now() - since) / 1000)) }), keepalive: true }).catch(() => {});
    };
  }, [playing]);
  async function search(page = 1) {
    const q = (page === 1 ? query : searched).trim();
    if (!q) return;
    const id = ++current.current;
    setBusy(true); setError(""); setPlaying(null); setResults(null);
    try {
      const data = await api<Results>(`/chat/videos?q=${encodeURIComponent(q)}&page=${page}`);
      if (current.current === id) { setResults(data); setSearched(q); }
    } catch (e) {
      if (current.current === id) setError(e instanceof Error ? tx(e.message) : tx("视频加载失败，请重试"));
    } finally { if (current.current === id) setBusy(false); }
  }
  async function play(id: string) {
    const task = ++current.current;
    setBusy(true); setError(""); setPlaying(null);
    try {
      const data = await api<Playback>(`/chat/videos/${id}`);
      if (current.current === task) setPlaying(data);
    } catch (e) {
      if (current.current === task) setError(e instanceof Error ? tx(e.message) : tx("视频加载失败，请重试"));
    } finally { if (current.current === task) setBusy(false); }
  }
  return <>
    <Heading title={tx("讲解视频")} />
    <p>{tx("搜索 B 站校园学习公开视频，使用播放器控制暂停、进度和全屏。")}</p>
    <form className="video-search" onSubmit={e => { e.preventDefault(); void search(); }}>
      <input aria-label={tx("搜索知识点或课程")} placeholder={tx("搜索知识点或课程")} maxLength={100} value={query} onChange={e => setQuery(e.target.value)} />
      <button className="primary" disabled={busy || !query.trim()}>{tx("搜索")}</button>
    </form>
    {busy && <p role="status">{tx("加载中…")}</p>}
    {error && <p role="alert">{error}</p>}
    {playing && <section className="video-player">
      <h2>{playing.title}</h2>
      <iframe key={playing.id} src={playing.embed_url} title={playing.title} allow="fullscreen; picture-in-picture" allowFullScreen referrerPolicy="strict-origin-when-cross-origin" sandbox="allow-scripts allow-same-origin allow-presentation" />
      <button onClick={() => setPlaying(null)}>{tx("关闭")}</button>
      <p>{tx("视频由第三方平台提供，无法播放时请重试或选择其他视频。")}</p>
    </section>}
    {results && <>
      {!results.items.length && <p role="status">{tx("没有找到相关讲解视频，请换个关键词")}</p>}
      <div className="video-results">{results.items.map(item => <section key={item.id}>
        <h2>{item.title}</h2><p>{item.author} · {item.duration}</p>
        <button disabled={busy} onClick={() => void play(item.id)}>{tx("播放视频")}</button>
      </section>)}</div>
      <div className="video-pagination">
        <button disabled={busy || results.page === 1} onClick={() => void search(results.page - 1)}>{tx("上一页")}</button>
        <span>{results.page}</span>
        <button disabled={busy || !results.has_more} onClick={() => void search(results.page + 1)}>{tx("下一页")}</button>
      </div>
    </>}
  </>;
}
