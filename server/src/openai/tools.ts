export const toolDefinitions = [
  {
    type: "function",
    function: {
      name: "memory_save",
      description: "Save a memory key/value. Use for things the user wants remembered.",
      parameters: {
        type: "object",
        properties: {
          key: { type: "string", description: "E.g., 'name', 'preference', 'note'" },
          value: { type: "string", description: "The value to store" }
        },
        required: ["key", "value"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "memory_search",
      description: "Search stored memories by keyword.",
      parameters: {
        type: "object",
        properties: {
          query: { type: "string" }
        },
        required: ["query"]
      }
    }
  },
  {
    type: "function",
    function: {
      name: "memory_forget",
      description: "Remove memories created today.",
      parameters: { type: "object", properties: {} }
    }
  },
  {
    type: "function",
    function: {
      name: "memory_list",
      description: "List recent memories.",
      parameters: {
        type: "object",
        properties: { limit: { type: "number", default: 50 } }
      }
    }
  }
] as const;

