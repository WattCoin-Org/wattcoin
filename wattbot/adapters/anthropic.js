/**
 * WattBot Anthropic Adapter
 * Handles Claude models via Anthropic Messages API.
 */

class AnthropicAdapter {
  constructor(config) {
    this.apiKey = config.apiKey || "";
    this.model = config.model || "claude-sonnet-4-20250514";
    this.baseUrl = "https://api.anthropic.com/v1";
  }
  
  static getDefaultModels() {
    return ["claude-sonnet-4-20250514", "claude-haiku-4-5-20251001"];
  }
  
  async validateKey() {
    try {
      // Anthropic doesn't have a /models list endpoint — do a minimal test
      const response = await fetch(`${this.baseUrl}/messages`, {
        method: "POST",
        headers: this._headers(),
        body: JSON.stringify({
          model: this.model,
          max_tokens: 10,
          messages: [{ role: "user", content: "hi" }]
        })
      });
      if (response.ok) {
        return { valid: true, models: AnthropicAdapter.getDefaultModels() };
      }
      const err = await response.json().catch(() => ({}));
      return { valid: false, error: err.error?.message || `HTTP ${response.status}` };
    } catch (e) {
      return { valid: false, error: e.message };
    }
  }
  
  async sendMessage(systemPrompt, messages, screenshot) {
    const apiMessages = [];
    
    for (const msg of messages) {
      if (msg.role === "user" && screenshot && msg === messages[messages.length - 1]) {
        // Attach screenshot to last user message
        apiMessages.push({
          role: "user",
          content: [
            { type: "text", text: msg.content },
            {
              type: "image",
              source: {
                type: "base64",
                media_type: "image/jpeg",
                data: screenshot.replace(/^data:image\/\w+;base64,/, "")
              }
            }
          ]
        });
      } else {
        apiMessages.push({ role: msg.role, content: msg.content });
      }
    }
    
    const body = {
      model: this.model,
      max_tokens: 1000,
      system: systemPrompt,
      messages: apiMessages
    };
    
    const response = await fetch(`${this.baseUrl}/messages`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify(body)
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.error?.message || `API error: ${response.status}`);
    }
    
    const data = await response.json();
    const text = data.content?.map(c => c.text).join("") || "";
    
    return {
      text,
      usage: data.usage || {},
      finishReason: data.stop_reason
    };
  }
  
  supportsVision() {
    return true; // All Claude models support vision
  }
  
  estimateCost(inputTokens, outputTokens) {
    const pricing = {
      "claude-sonnet-4-20250514": { input: 3.00, output: 15.00 },
      "claude-haiku-4-5-20251001": { input: 0.80, output: 4.00 }
    };
    const price = pricing[this.model] || { input: 3.00, output: 15.00 };
    const inputCost = (inputTokens / 1_000_000) * price.input;
    const outputCost = (outputTokens / 1_000_000) * price.output;
    return { inputCost, outputCost, total: inputCost + outputCost };
  }
  
  _headers() {
    return {
      "Content-Type": "application/json",
      "x-api-key": this.apiKey,
      "anthropic-version": "2023-06-01",
      "anthropic-dangerous-direct-browser-access": "true"
    };
  }
}

if (typeof window !== "undefined") {
  window.__wattbot_AnthropicAdapter = AnthropicAdapter;
}
