import { useState, useCallback } from 'react';

export function useStreamingFetch() {
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState(null);

  const streamFetch = useCallback(async (url, options, onChunk) => {
    setIsStreaming(true);
    setError(null);

    try {
      const response = await fetch(url, options);
      
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value, { stream: true });
        onChunk(chunk);
      }

      setIsStreaming(false);
    } catch (err) {
      setError(err.message);
      setIsStreaming(false);
      throw err;
    }
  }, []);

  return { streamFetch, isStreaming, error };
}
