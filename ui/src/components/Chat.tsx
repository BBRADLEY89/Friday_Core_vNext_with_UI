import React, { useRef, useState } from "react";
import { streamChat } from "../lib/chatApi";

type Msg = { role: "user"|"assistant"; content: string };

export default function Chat() {
  const [messages, setMessages] = useState<Msg[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);

  async function send() {
    const content = inputRef.current?.value?.trim();
    if (!content || busy) return;
    inputRef.current!.value = "";
    const nextMsgs = [...messages, { role: "user", content }];
    setMessages(nextMsgs);
    setBusy(true);

    let assistantText = "";
    await streamChat(nextMsgs, (chunk) => {
      assistantText += chunk;
      // live render
      setMessages([...nextMsgs, { role: "assistant", content: assistantText }]);
    });

    setBusy(false);
  }

  return (
    <div className="p-4 max-w-3xl mx-auto">
      <div className="space-y-2 mb-3">
        {messages.map((m, i) => (
          <div
            key={i}
            className={m.role === "user" ? "bg-slate-800/40 p-2 rounded" : "bg-slate-700/40 p-2 rounded"}
          >
            {/* guard: in case any JSON slips through, hide it */}
            <pre className="whitespace-pre-wrap break-words">
              {m.content.startsWith('{"tool_name"') ? "" : m.content}
            </pre>
          </div>
        ))}
      </div>
      <div className="flex gap-2">
        <input ref={inputRef} className="flex-1 bg-black/30 border border-slate-600 rounded px-3 py-2" placeholder="Type your message…" />
        <button onClick={send} disabled={busy} className="px-4 py-2 rounded bg-blue-600 disabled:opacity-40">
          {busy ? "Thinking…" : "Send"}
        </button>
      </div>
    </div>
  );
}

