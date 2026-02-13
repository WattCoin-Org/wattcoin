/**
 * WattBot OpenAI-Compatible Adapter
 * Handles: OpenAI GPT, xAI Grok, Ollama, LM Studio, any OpenAI-compatible endpoint.
 */

class OpenAIAdapter {
  constructor(config) {
    this.apiKey = config.apiKey || "";
    this.baseUrl = config.baseUrl || "https://api.openai.com/v1";
    this.model = config.model || "gpt-4o";
    this.provider = config.provider || "openai"; // openai, xai, ollama, custom
  }
  
  /**
   * Get default base URLs per provider.
   */
  static getBaseUrl(provider) {
    const urls = {
      openai: "https://api.openai.com/v1",
      xai: "https://api.x.ai/v1",
      google: "https://generativelanguage.googleapis.com/v1beta/openai",
      deepseek: "https://api.deepseek.com/v1",
      ollama: "http://localhost:11434/v1",
      lmstudio: "http://localhost:1234/v1"
    };
    return urls[provider] || urls.openai;
  }
  
  /**
   * Get default models per provider.
   */
  static getDefaultModels(provider) {
    const models = {
      openai: ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo"],
      xai: ["grok-2", "grok-2-vision"],
      ollama: ["llama3.1", "mistral", "codellama"],
      lmstudio: ["loaded-model"]
    };
    return models[provider] || models.openai;
  }
  
  /**
   * Test API key validity.
   */
  async validateKey() {
    try {
      const response = await fetch(`${this.baseUrl}/models`, {
        headers: this._headers()
      });
      if (response.ok) {
        const data = await response.json();
        return { valid: true, models: data.data?.map(m => m.id) || [] };
      }
      return { valid: false, error: `API returned ${response.status}` };
    } catch (e) {
      return { valid: false, error: e.message };
    }
  }
  
  /**
   * Send message to LLM and get response.
   * @param {string} systemPrompt - System instructions
   * @param {Array} messages - Conversation history [{role, content}]
   * @param {string|null} screenshot - Base64 screenshot data URL (optional)
   * @returns {object} {text, usage}
   */
  async sendMessage(systemPrompt, messages, screenshot) {
    const apiMessages = [
      { role: "system", content: systemPrompt }
    ];
    
    // Add conversation history
    for (const msg of messages) {
      if (msg.role === "user" && screenshot && msg === messages[messages.length - 1]) {
        // Last user message — attach screenshot if provided
        apiMessages.push({
          role: "user",
          content: [
            { type: "text", text: msg.content },
            { type: "image_url", image_url: { url: screenshot, detail: "low" } }
          ]
        });
      } else {
        apiMessages.push({ role: msg.role, content: msg.content });
      }
    }
    
    const body = {
      model: this.model,
      messages: apiMessages,
      temperature: 0.2,
      max_tokens: 1000
    };
    
    const response = await fetch(`${this.baseUrl}/chat/completions`, {
      method: "POST",
      headers: this._headers(),
      body: JSON.stringify(body)
    });
    
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      const errorMsg = errorData.error?.message || `API error: ${response.status}`;
      throw new Error(errorMsg);
    }
    
    const data = await response.json();
    const choice = data.choices?.[0];
    
    if (!choice) {
      throw new Error("No response from API");
    }
    
    return {
      text: choice.message?.content || "",
      usage: data.usage || {},
      finishReason: choice.finish_reason
    };
  }
  
  /**
   * Check if current model supports vision (screenshots).
   */
  supportsVision() {
    const visionModels = [
      "gpt-4o", "gpt-4o-mini", "gpt-4-turbo",
      "grok-2-vision",
      "llava", "llama3.2-vision"
    ];
    return visionModels.some(vm => this.model.includes(vm));
  }
  
  /**
   * Estimate token cost for display.
   */
  estimateCost(inputTokens, outputTokens) {
    // Rough pricing per 1M tokens (varies by model)
    const pricing = {
      "gpt-4o": { input: 2.50, output: 10.00 },
      "gpt-4o-mini": { input: 0.15, output: 0.60 },
      "gpt-4-turbo": { input: 10.00, output: 30.00 },
      "grok-2": { input: 2.00, output: 10.00 }
    };
    
    const price = pricing[this.model] || { input: 2.50, output: 10.00 };
    const inputCost = (inputTokens / 1_000_000) * price.input;
    const outputCost = (outputTokens / 1_000_000) * price.output;
    return { inputCost, outputCost, total: inputCost + outputCost };
  }
  
  _headers() {
    const headers = { "Content-Type": "application/json" };
    if (this.apiKey) {
      headers["Authorization"] = `Bearer ${this.apiKey}`;
    }
    return headers;
  }
}

// Export
if (typeof window !== "undefined") {
  window.__wattbot_OpenAIAdapter = OpenAIAdapter;
}
