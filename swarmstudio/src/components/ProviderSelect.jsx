import { useState } from 'react';
import { PROVIDERS } from '../config/providers';
import { fetchModels } from '../utils/api';

export default function ProviderSelect({ 
  provider, 
  model, 
  customModel,
  baseUrl,
  apiKey,
  onChange 
}) {
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [refreshedModels, setRefreshedModels] = useState(null);

  const currentProvider = PROVIDERS[provider];
  const availableModels = refreshedModels || currentProvider?.models || [];

  const handleRefreshModels = async () => {
    if (!apiKey) {
      alert('Please enter an API key first');
      return;
    }

    setIsRefreshing(true);
    try {
      const result = await fetchModels(provider, apiKey, baseUrl);
      if (result.models && result.models.length > 0) {
        setRefreshedModels(result.models);
      } else {
        alert('No models found or refresh failed');
      }
    } catch (err) {
      alert(`Failed to refresh models: ${err.message}`);
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div className="space-y-3">
      {/* Provider dropdown */}
      <div>
        <label className="block text-xs font-mono text-text-secondary mb-1.5">
          Provider
        </label>
        <select
          value={provider}
          onChange={(e) => onChange({ provider: e.target.value })}
          className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors"
        >
          {Object.entries(PROVIDERS).map(([key, config]) => (
            <option 
              key={key} 
              value={key} 
              disabled={config.disabled}
              title={config.disabledReason}
            >
              {config.name} {config.disabled ? `(${config.disabledReason})` : ''}
            </option>
          ))}
        </select>
      </div>

      {/* Model dropdown */}
      <div>
        <div className="flex items-center justify-between mb-1.5">
          <label className="text-xs font-mono text-text-secondary">
            Model
          </label>
          {currentProvider && !currentProvider.noRefresh && (
            <button
              onClick={handleRefreshModels}
              disabled={isRefreshing || !apiKey}
              className="text-xs text-accent-amber hover:text-accent-orange disabled:text-text-muted disabled:cursor-not-allowed transition-colors"
            >
              {isRefreshing ? 'Refreshing...' : '↻ Refresh'}
            </button>
          )}
        </div>
        <select
          value={model}
          onChange={(e) => onChange({ model: e.target.value })}
          disabled={!currentProvider || currentProvider.disabled}
          className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors disabled:opacity-50"
        >
          {availableModels.map((m) => (
            <option key={m} value={m}>{m}</option>
          ))}
        </select>
      </div>

      {/* Custom model override */}
      <div>
        <label className="block text-xs font-mono text-text-secondary mb-1.5">
          Custom Model (optional)
        </label>
        <input
          type="text"
          value={customModel || ''}
          onChange={(e) => onChange({ customModel: e.target.value })}
          placeholder="Override model name"
          className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors placeholder:text-text-muted"
        />
      </div>

      {/* Base URL (for custom provider) */}
      {currentProvider?.showBaseUrl && (
        <div>
          <label className="block text-xs font-mono text-text-secondary mb-1.5">
            Base URL
          </label>
          <input
            type="text"
            value={baseUrl || ''}
            onChange={(e) => onChange({ baseUrl: e.target.value })}
            placeholder="https://your-api-endpoint.com/v1"
            className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors placeholder:text-text-muted"
          />
        </div>
      )}
    </div>
  );
}
