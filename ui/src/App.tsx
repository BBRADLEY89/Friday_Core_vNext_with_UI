import React, { useEffect, useMemo, useRef, useState } from "react";
import "./styles.css";

type Msg = { role: "user" | "assistant"; content: string };
const BASE_KEY = "FRIDAY_BASE";
const CHAT_KEY = "FRIDAY_CHAT";
const DEFAULT_BASE = "http://127.0.0.1:8767";

type Mode = "idle" | "listening" | "thinking" | "speaking";

export default function App() {
  // state
  const [base, setBase] = useState<string>(() => localStorage.getItem(BASE_KEY) || DEFAULT_BASE);
  const [chat, setChat] = useState<Msg[]>(() => {
    try { return JSON.parse(localStorage.getItem(CHAT_KEY) || "[]"); } catch { return []; }
  });
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const [mode, setMode] = useState<Mode>("idle");

  const audioRef = useRef<HTMLAudioElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const mediaRecRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);

  // persist base + chat
  useEffect(() => { localStorage.setItem(BASE_KEY, base); }, [base]);
  useEffect(() => { localStorage.setItem(CHAT_KEY, JSON.stringify(chat.slice(-200))); scrollToEnd(); }, [chat]);

  function scrollToEnd() {
    requestAnimationFrame(() => listRef.current?.scrollTo({ top: 999999, behavior: "smooth" }));
  }

  async function runTool(tool_name: string, args: Record<string, any>) {
    const r = await fetch(`${base}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tool_name, args })
    });
    return r.json();
  }

  async function speak(text: string) {
    try {
      setMode("speaking");
      const r = await fetch(`${base}/voice/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text })
      });
      if (!r.ok) throw new Error("TTS failed");
      const buf = await r.arrayBuffer();
      const blob = new Blob([buf], { type: "audio/mpeg" });
      const url = URL.createObjectURL(blob);
      if (audioRef.current) {
        audioRef.current.src = url;
        await audioRef.current.play().catch(() => {});
      }
    } finally {
      setMode("idle");
    }
  }

  async function sendMessage(text: string) {
    const msg = text.trim();
    if (!msg) return;
    const next = [...chat, { role: "user", content: msg }];
    setChat(next);
    setInput("");
    setBusy(true);
    setMode("thinking");
    try {
      const r = await fetch(`${base}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: next })
      });
      const data = await r.json();
      const reply = (data?.content ?? "").toString();
      setChat([...next, { role: "assistant", content: reply }]);
      // auto-speak reply
      await speak(reply);
    } catch (e: any) {
      setChat([...next, { role: "assistant", content: "⚠️ Error: " + (e?.message || e) }]);
    } finally {
      setBusy(false);
      setMode("idle");
    }
  }

  // --- Voice toggle (on/off) ---
  async function toggleVoice() {
    if (voiceOn) {
      // Stop
      setVoiceOn(false);
      const mr = mediaRecRef.current;
      if (mr && mr.state !== "inactive") mr.stop();
      return;
    }
    // Start listening
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = (ev) => { chunksRef.current.push(ev.data); };
      mr.onstop = async () => {
        try {
          const audioBlob = new Blob(chunksRef.current, { type: "audio/webm" });
          const form = new FormData();
          form.append("file", audioBlob, "input.webm"); // backend accepts 'file'
          setMode("thinking");
          const tr = await fetch(`${base}/voice/transcribe`, { method: "POST", body: form });
          const td = await tr.json();
          const text = td?.text || td?.transcript || "";
          if (text) await sendMessage(text);
        } finally {
          stream.getTracks().forEach(t => t.stop());
          setMode("idle");
        }
      };
      setVoiceOn(true);
      setMode("listening");
      mr.start();
    } catch (e) {
      console.error(e);
      setVoiceOn(false);
      setMode("idle");
    }
  }

  // remember / forget buttons
  async function rememberThis() {
    const txt = input.trim() || (chat[chat.length - 1]?.content || "");
    if (!txt) return;
    await runTool("memory_save", { text: txt });
  }

  async function forgetToday() {
    await runTool("journal_write", { text: "User requested to forget transient details today." });
  }

  const ringClass = useMemo(() => {
    if (mode === "listening") return "ring ring-listening";
    if (mode === "thinking") return "ring ring-thinking";
    if (mode === "speaking") return "ring ring-speaking";
    return "ring";
  }, [mode]);

  return (
    <div className="min-h-screen bg-ink text-white">
      {/* Header */}
      <header className="flex items-center justify-between px-5 py-4">
        <div className="flex items-center gap-3">
          <div className="logo-infinity" />
          <div className="text-xl tracking-wide font-semibold">FRIDAY • UNIVERSE</div>
        </div>
        {/* tiny settings input for Base URL */}
        <div className="flex items-center gap-2">
          <span className="text-xs opacity-60">Base</span>
          <input
            value={base}
            onChange={e => setBase(e.target.value)}
            className="bg-white/5 border border-white/10 rounded px-2 py-1 text-sm w-[260px] outline-none"
          />
        </div>
      </header>

      {/* Center pulsing infinity */}
      <div className="flex items-center justify-center pt-6 pb-2">
        <div className={ringClass}>
          <div className="infinity-core" />
        </div>
      </div>

      {/* Chat list */}
      <div ref={listRef} className="mx-auto max-w-3xl h-[48vh] overflow-y-auto px-4 space-y-3">
        {chat.map((m, i) => (
          <div key={i} className={`bubble ${m.role === "user" ? "user" : "assistant"}`}>
            {m.content}
          </div>
        ))}
      </div>

      {/* Input & actions */}
      <div className="mx-auto max-w-3xl px-4 py-4">
        <div className="flex items-center gap-2">
          <button
            onClick={toggleVoice}
            className={`btn ${voiceOn ? "btn-on" : ""}`}
            title="Toggle voice mode"
          >
            {voiceOn ? "🎤 Voice: ON" : "🎤 Voice: OFF"}
          </button>

          <input
            className="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-3 outline-none"
            placeholder="Type your message…"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => { if (e.key === "Enter" && !busy) sendMessage(input); }}
          />
          <button onClick={() => !busy && sendMessage(input)} className="btn">Send ↵</button>
        </div>

        <div className="flex items-center gap-2 mt-3">
          <button onClick={rememberThis} className="btn-secondary">Remember this</button>
          <button onClick={forgetToday} className="btn-secondary">Forget today</button>
          <span className="text-xs opacity-60 ml-auto">Mode: {mode}</span>
        </div>
      </div>

      <audio ref={audioRef} className="hidden" />
    </div>
  );
}