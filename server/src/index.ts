import "dotenv/config";
import express from "express";
import cors from "cors";
import { runChatWithTools } from "./openai/bridge.js";

const app = express();
app.use(cors());
app.use(express.json());

app.get("/api/health", (_, res) => res.json({ status: "ok", timezone: Intl.DateTimeFormat().resolvedOptions().timeZone }));

// Streaming via chunked text (simpler than SSE but fine for now)
app.post("/api/chat", async (req, res) => {
  try {
    const messages = req.body?.messages ?? [];
    res.setHeader("Content-Type", "text/plain; charset=utf-8");
    res.setHeader("Transfer-Encoding", "chunked");

    await runChatWithTools(messages, (delta) => {
      res.write(delta);
    });

    res.end();
  } catch (e:any) {
    console.error(e);
    res.status(500).json({ error: e.message || "chat_failed" });
  }
});

const PORT = Number(process.env.PORT || 8767);
app.listen(PORT, () => {
  console.log(`[Friday] Server on http://127.0.0.1:${PORT}`);
});

