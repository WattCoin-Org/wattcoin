const API_URL = import.meta.env.VITE_API_URL || "https://wattcoin-production-81a7.up.railway.app";

export async function testKey(provider, apiKey, baseUrl = "", model = "") {
  const res = await fetch(`${API_URL}/api/v1/swarmstudio/test-key`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl, model })
  });
  return res.json();
}

export async function fetchModels(provider, apiKey, baseUrl = "") {
  const res = await fetch(`${API_URL}/api/v1/swarmstudio/models`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ provider, api_key: apiKey, base_url: baseUrl })
  });
  return res.json();
}

export async function streamChat(provider, model, apiKey, baseUrl, messages, maxTokens, onToken, onUsage, onDone, onError) {
  try {
    const response = await fetch(`${API_URL}/api/v1/swarmstudio/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        model,
        api_key: apiKey,
        base_url: baseUrl,
        messages,
        max_tokens: maxTokens
      })
    });

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}: ${response.statusText}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      
      // Process complete SSE messages (ended with \n\n)
      const lines = buffer.split('\n\n');
      buffer = lines.pop() || ''; // Keep incomplete message in buffer

      for (const line of lines) {
        if (!line.trim() || !line.startsWith('data: ')) continue;

        const jsonStr = line.replace('data: ', '').trim();
        if (!jsonStr) continue;

        try {
          const event = JSON.parse(jsonStr);

          if (event.type === 'token' && event.content) {
            onToken(event.content);
          } else if (event.type === 'usage') {
            onUsage(event.input_tokens || 0, event.output_tokens || 0);
          } else if (event.type === 'done') {
            onDone();
            return;
          } else if (event.type === 'error') {
            onError(event.message || 'Unknown error');
            return;
          }
        } catch (parseErr) {
          console.error('Failed to parse SSE event:', jsonStr, parseErr);
        }
      }
    }

    // Stream ended without explicit done event
    onDone();
  } catch (err) {
    onError(err.message || 'Connection failed');
  }
}
