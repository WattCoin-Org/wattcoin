export const PROVIDERS = {
  openai: {
    name: "OpenAI",
    placeholder: "sk-...",
    help: "https://platform.openai.com/api-keys",
    baseUrl: "https://api.openai.com/v1",
    models: ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano", "o3", "o3-mini", "o4-mini"],
    adapter: "openai-compatible"
  },
  anthropic: {
    name: "Anthropic",
    placeholder: "sk-ant-...",
    help: "https://console.anthropic.com/settings/keys",
    baseUrl: "https://api.anthropic.com/v1",
    models: ["claude-opus-4-6", "claude-sonnet-4-20250514", "claude-opus-4-5-20250918", "claude-haiku-4-5-20251001"],
    adapter: "anthropic",
    noRefresh: true
  },
  xai: {
    name: "xAI",
    placeholder: "xai-...",
    help: "https://console.x.ai/",
    baseUrl: "https://api.x.ai/v1",
    models: ["grok-3", "grok-3-fast", "grok-3-mini", "grok-3-mini-fast", "grok-code-fast-1", "grok-4-fast-reasoning", "grok-4-1-fast-reasoning", "grok-4-1-fast-non-reasoning"],
    adapter: "openai-compatible"
  },
  google: {
    name: "Google",
    placeholder: "AIza...",
    help: "https://aistudio.google.com/apikey",
    baseUrl: "https://generativelanguage.googleapis.com/v1beta/openai",
    models: ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-2.0-flash-lite"],
    adapter: "openai-compatible"
  },
  deepseek: {
    name: "DeepSeek",
    placeholder: "sk-...",
    help: "https://platform.deepseek.com/api_keys",
    baseUrl: "https://api.deepseek.com/v1",
    models: ["deepseek-chat", "deepseek-reasoner"],
    adapter: "openai-compatible"
  },
  custom: {
    name: "Custom (OpenAI-compatible)",
    placeholder: "your-api-key",
    help: "Any OpenAI-compatible endpoint (LM Studio, vLLM, etc.)",
    baseUrl: "",
    models: ["default"],
    adapter: "openai-compatible",
    showBaseUrl: true
  },
  ollama: {
    name: "Ollama (Local)",
    disabled: true,
    disabledReason: "Available in desktop version",
    models: []
  },
  wsi: {
    name: "WSI (WattCoin SuperIntelligence)",
    disabled: true,
    disabledReason: "Coming Soon",
    models: []
  }
};
