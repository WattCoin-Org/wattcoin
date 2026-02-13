import { useState } from 'react';
import { PROVIDERS } from '../config/providers';
import { testKey } from '../utils/api';
import ProviderSelect from './ProviderSelect';
import StatusBadge from './StatusBadge';

export default function AgentCard({ agent, color, onUpdate, onDelete, canDelete }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState(null);

  const provider = PROVIDERS[agent.provider];

  const handleTestKey = async () => {
    if (!agent.apiKey) {
      setTestResult({ valid: false, message: 'Please enter an API key' });
      return;
    }

    setIsTesting(true);
    setTestResult(null);

    try {
      const result = await testKey(agent.provider, agent.apiKey, agent.baseUrl, agent.model);
      setTestResult(result);
    } catch (err) {
      setTestResult({ valid: false, message: `Error: ${err.message}` });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div className="bg-dark-card border border-dark-border rounded-lg overflow-hidden hover:border-dark-border-hover transition-colors">
      {/* Collapsed header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="w-full px-4 py-3 flex items-center justify-between text-left"
      >
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <div 
            className="w-3 h-3 rounded-full flex-shrink-0" 
            style={{ backgroundColor: color }}
          />
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium truncate">{agent.name}</div>
            <div className="text-xs text-text-secondary">{provider?.name || agent.provider}</div>
          </div>
        </div>
        <div className="flex items-center gap-3 flex-shrink-0">
          <StatusBadge status={agent.status || 'idle'} />
          <svg 
            className={`w-4 h-4 text-text-secondary transition-transform ${isExpanded ? 'rotate-180' : ''}`}
            fill="none" 
            viewBox="0 0 24 24" 
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </button>

      {/* Expanded content */}
      {isExpanded && (
        <div className="px-4 pb-4 space-y-4 border-t border-dark-border">
          {/* Agent name */}
          <div>
            <label className="block text-xs font-mono text-text-secondary mb-1.5 mt-4">
              Agent Name
            </label>
            <input
              type="text"
              value={agent.name}
              onChange={(e) => onUpdate({ name: e.target.value })}
              className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors"
            />
          </div>

          {/* Provider & Model selection */}
          <ProviderSelect
            provider={agent.provider}
            model={agent.model}
            customModel={agent.customModel}
            baseUrl={agent.baseUrl}
            apiKey={agent.apiKey}
            onChange={(updates) => onUpdate(updates)}
          />

          {/* API Key */}
          <div>
            <label className="block text-xs font-mono text-text-secondary mb-1.5">
              API Key
            </label>
            <div className="relative">
              <input
                type={showKey ? 'text' : 'password'}
                value={agent.apiKey || ''}
                onChange={(e) => onUpdate({ apiKey: e.target.value })}
                placeholder={provider?.placeholder || 'your-api-key'}
                autoComplete="off"
                data-1p-ignore
                data-lpignore="true"
                className="w-full px-3 py-2 pr-20 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors placeholder:text-text-muted"
              />
              <button
                onClick={() => setShowKey(!showKey)}
                className="absolute right-2 top-1/2 -translate-y-1/2 px-2 py-1 text-xs text-text-secondary hover:text-text-primary"
              >
                {showKey ? 'Hide' : 'Show'}
              </button>
            </div>
            {provider?.help && (
              <a 
                href={provider.help}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-accent-amber hover:text-accent-orange mt-1 inline-block"
              >
                Get API key →
              </a>
            )}
          </div>

          {/* Test Key button */}
          <button
            onClick={handleTestKey}
            disabled={isTesting || !agent.apiKey}
            className="w-full px-4 py-2 bg-dark-panel border border-dark-border rounded-lg text-sm font-medium hover:border-accent-amber transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isTesting ? 'Testing...' : 'Test API Key'}
          </button>

          {/* Test result */}
          {testResult && (
            <div className={`px-3 py-2 rounded-lg text-xs ${
              testResult.valid 
                ? 'bg-green-500/10 text-green-400 border border-green-500/20' 
                : 'bg-red-500/10 text-red-400 border border-red-500/20'
            }`}>
              {testResult.message || (testResult.valid ? 'API key is valid ✓' : 'API key is invalid')}
            </div>
          )}

          {/* System prompt */}
          <div>
            <label className="block text-xs font-mono text-text-secondary mb-1.5">
              System Prompt
            </label>
            <textarea
              value={agent.systemPrompt || ''}
              onChange={(e) => onUpdate({ systemPrompt: e.target.value })}
              placeholder="You are a helpful assistant..."
              rows={3}
              className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors placeholder:text-text-muted resize-none"
            />
          </div>

          {/* Delete button */}
          <button
            onClick={onDelete}
            disabled={!canDelete}
            className="w-full px-4 py-2 bg-red-500/10 border border-red-500/20 text-red-400 rounded-lg text-sm font-medium hover:bg-red-500/20 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            Delete Agent
          </button>
        </div>
      )}
    </div>
  );
}
