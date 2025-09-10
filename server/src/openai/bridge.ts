import { OpenAI } from "openai";
import { toolDefinitions } from "./tools.js";
import { memoryStore } from "../memory/MemoryStore.js";

const openai = new OpenAI({ apiKey: process.env.OPENAI_API_KEY! });

export async function runChatWithTools(messages: any[], onDelta?: (text: string) => void) {
  // 1) First call with tools enabled
  const resp = await openai.chat.completions.create({
    model: "gpt-4o-mini",
    messages,
    tools: toolDefinitions as any,
    tool_choice: "auto",
    stream: false
  });

  const choice = resp.choices[0];
  const toolCalls = choice.message.tool_calls;

  if (toolCalls && toolCalls.length > 0) {
    // 2) Execute each tool call and append results as tool messages
    const toolResults: any[] = [];
    for (const call of toolCalls) {
      const name = call.function.name;
      const args = JSON.parse(call.function.arguments || "{}");

      let result: any = null;

      try {
        if (name === "memory_save") {
          const key = String(args.key ?? "").trim();
          const value = String(args.value ?? "").trim();
          result = await memoryStore.saveKV(key, value);
        } else if (name === "memory_search") {
          result = await memoryStore.search(String(args.query ?? ""));
        } else if (name === "memory_forget") {
          result = await memoryStore.forgetToday();
        } else if (name === "memory_list") {
          const limit = Number(args.limit ?? 50);
          result = await memoryStore.listAll(limit);
        } else {
          result = { error: `Unknown tool ${name}` };
        }
      } catch (e: any) {
        result = { error: e?.message || String(e) };
      }

      toolResults.push({
        role: "tool",
        tool_call_id: call.id,
        name,
        content: JSON.stringify(result)
      });
    }

    // 3) Follow-up call: provide tool results, get final natural language
    const followup = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        ...messages,
        { role: "assistant", tool_calls: toolCalls },
        ...toolResults
      ],
      stream: true
    });

    // 4) Stream only natural language text to client
    let finalText = "";
    for await (const chunk of followup) {
      const delta = chunk.choices[0]?.delta?.content ?? "";
      if (delta) {
        finalText += delta;
        onDelta?.(delta);
      }
    }
    return finalText;
  }

  // No tools, return the assistant text directly
  const text = choice.message.content ?? "";
  onDelta?.(text);
  return text;
}

