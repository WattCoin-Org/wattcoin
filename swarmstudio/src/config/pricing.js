// Prices per 1M tokens (USD) — update quarterly
export const PRICING = {
  "gpt-4o":          { input: 2.50,  output: 10.00 },
  "gpt-4o-mini":     { input: 0.15,  output: 0.60  },
  "gpt-4.1":         { input: 2.00,  output: 8.00  },
  "gpt-4.1-mini":    { input: 0.40,  output: 1.60  },
  "gpt-4.1-nano":    { input: 0.10,  output: 0.40  },
  "o3":              { input: 2.00,  output: 8.00  },
  "o3-mini":         { input: 1.10,  output: 4.40  },
  "o4-mini":         { input: 1.10,  output: 4.40  },
  "claude-opus-4-6":              { input: 5.00,  output: 25.00 },
  "claude-sonnet-4-20250514":     { input: 3.00,  output: 15.00 },
  "claude-opus-4-5-20250918":     { input: 15.00, output: 75.00 },
  "claude-haiku-4-5-20251001":    { input: 0.80,  output: 4.00  },
  "grok-3":          { input: 3.00,  output: 15.00 },
  "grok-3-fast":     { input: 5.00,  output: 25.00 },
  "grok-3-mini":     { input: 0.30,  output: 0.50  },
  "grok-3-mini-fast":{ input: 0.60,  output: 1.00  },
  "grok-code-fast-1":             { input: 0.20,  output: 1.50  },
  "grok-4-fast-reasoning":        { input: 0.20,  output: 0.50  },
  "grok-4-1-fast-reasoning":      { input: 0.20,  output: 0.50  },
  "grok-4-1-fast-non-reasoning":  { input: 0.20,  output: 0.50  },
  "gemini-2.5-flash":{ input: 0.15,  output: 0.60  },
  "gemini-2.5-pro":  { input: 1.25,  output: 10.00 },
  "gemini-2.0-flash":{ input: 0.10,  output: 0.40  },
  "gemini-2.0-flash-lite":        { input: 0.075, output: 0.30  },
  "deepseek-chat":   { input: 0.27,  output: 1.10  },
  "deepseek-reasoner":{ input: 0.55, output: 2.19  },
  "_default":        { input: 1.00,  output: 3.00  }
};

export function estimateCost(model, inputTokens, outputTokens) {
  const rates = PRICING[model] || PRICING["_default"];
  return ((inputTokens * rates.input) + (outputTokens * rates.output)) / 1_000_000;
}
