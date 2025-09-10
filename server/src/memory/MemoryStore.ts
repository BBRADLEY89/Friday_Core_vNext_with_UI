import fs from "fs";
import path from "path";
import Database from "better-sqlite3";

export type MemoryItem = {
  id: string;
  key: string;
  value: string;
  created_at: string;
};

const DATA_DIR = path.resolve(process.cwd(), "data");
const DB_PATH = path.join(DATA_DIR, "friday.db");
const JSONL_PATH = path.join(DATA_DIR, "memory.jsonl");

export class MemoryStore {
  private db?: Database.Database;
  private useJsonl = false;

  constructor() {
    if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR, { recursive: true });
    try {
      this.db = new Database(DB_PATH);
      this.db
        .prepare(
          `CREATE TABLE IF NOT EXISTS memories (
            id TEXT PRIMARY KEY,
            key TEXT,
            value TEXT,
            created_at TEXT
          )`
        )
        .run();
    } catch (e) {
      console.warn("[MemoryStore] SQLite unavailable, falling back to JSONL.", e);
      this.useJsonl = true;
      if (!fs.existsSync(JSONL_PATH)) fs.writeFileSync(JSONL_PATH, "");
    }
  }

  private nowISO() {
    return new Date().toISOString();
  }

  async saveKV(key: string, value: string) {
    const item: MemoryItem = {
      id: (globalThis as any).crypto?.randomUUID?.() || Math.random().toString(36).slice(2),
      key,
      value,
      created_at: this.nowISO()
    };
    if (this.useJsonl) {
      fs.appendFileSync(JSONL_PATH, JSON.stringify(item) + "\n");
      return item;
    }
    this.db!.prepare(
      `INSERT INTO memories (id, key, value, created_at) VALUES (@id, @key, @value, @created_at)`
    ).run(item);
    return item;
  }

  async saveName(name: string) {
    return this.saveKV("name", name);
  }

  async listAll(limit = 200) {
    if (this.useJsonl) {
      const content = fs.existsSync(JSONL_PATH) ? fs.readFileSync(JSONL_PATH, "utf8") : "";
      const lines = content.trim() ? content.trim().split("\n") : [];
      return lines.slice(-limit).map(l => JSON.parse(l) as MemoryItem);
    }
    return this.db!.prepare(`SELECT * FROM memories ORDER BY created_at DESC LIMIT ?`).all(limit);
  }

  async search(query: string, limit = 50) {
    if (this.useJsonl) {
      const content = fs.existsSync(JSONL_PATH) ? fs.readFileSync(JSONL_PATH, "utf8") : "";
      const lines = content.trim() ? content.trim().split("\n") : [];
      return lines
        .map(l => JSON.parse(l) as MemoryItem)
        .filter(r => r.key.includes(query) || r.value.toLowerCase().includes(query.toLowerCase()))
        .slice(0, limit);
    }
    return this.db!.prepare(
      `SELECT * FROM memories WHERE key LIKE ? OR value LIKE ? ORDER BY created_at DESC LIMIT ?`
    ).all(`%${query}%`, `%${query}%`, limit);
  }

  async forgetToday() {
    const today = new Date().toISOString().slice(0, 10);
    if (this.useJsonl) {
      const content = fs.existsSync(JSONL_PATH) ? fs.readFileSync(JSONL_PATH, "utf8") : "";
      const lines = content.trim() ? content.trim().split("\n") : [];
      const kept = lines.filter(l => {
        const r = JSON.parse(l) as MemoryItem;
        return !r.created_at.startsWith(today);
      });
      fs.writeFileSync(JSONL_PATH, kept.join("\n") + (kept.length ? "\n" : ""));
      return { removed: lines.length - kept.length };
    }
    const res = this.db!.prepare(`DELETE FROM memories WHERE substr(created_at,1,10) = ?`).run(today);
    return { removed: (res as any).changes ?? 0 };
  }
}

export const memoryStore = new MemoryStore();

