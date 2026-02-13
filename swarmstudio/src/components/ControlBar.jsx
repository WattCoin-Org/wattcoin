export default function ControlBar({ 
  prompt, 
  rounds, 
  onPromptChange, 
  onRoundsChange, 
  onStart, 
  onStop,
  canStart,
  isRunning,
  currentRound,
  totalRounds,
  currentAgentName,
  onSaveSession,
  onClearSession,
  sessionSaved,
  onExport,
  exportStatus,
  hasMessages
}) {
  return (
    <div className="bg-dark-panel border-b border-dark-border p-4">
      <div className="flex gap-4 items-start">
        {/* Prompt input */}
        <div className="flex-1">
          <textarea
            value={prompt}
            onChange={(e) => onPromptChange(e.target.value)}
            placeholder="Enter your prompt..."
            rows={2}
            disabled={isRunning}
            className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors placeholder:text-text-muted resize-none disabled:opacity-50 disabled:cursor-not-allowed"
          />
        </div>

        {/* Rounds selector */}
        <div className="w-32">
          <label className="block text-xs font-mono text-text-secondary mb-1.5">
            Rounds
          </label>
          <select
            value={rounds}
            onChange={(e) => onRoundsChange(parseInt(e.target.value))}
            disabled={isRunning}
            className="w-full px-3 py-2 bg-dark-bg border border-dark-border rounded-lg text-sm focus:outline-none focus:border-accent-amber transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {[1, 2, 3, 4, 5, 6, 7, 8, 9, 10].map(n => (
              <option key={n} value={n}>{n}</option>
            ))}
          </select>
        </div>

        {/* Action buttons */}
        <div className="pt-6 flex gap-2">
          {!isRunning ? (
            <button
              onClick={onStart}
              disabled={!canStart}
              className="px-6 py-2 gradient-accent text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              Start
            </button>
          ) : (
            <button
              onClick={onStop}
              className="px-6 py-2 bg-red-500 hover:bg-red-600 text-white rounded-lg font-medium transition-colors whitespace-nowrap"
            >
              Stop
            </button>
          )}

          <button
            onClick={onSaveSession}
            disabled={isRunning}
            className="px-3 py-2 bg-dark-card border border-dark-border text-text-secondary rounded-lg text-sm hover:text-accent-amber hover:border-accent-amber transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            title="Save agents, keys & settings to browser"
          >
            {sessionSaved ? '✓ Saved' : 'Save'}
          </button>

          <button
            onClick={onClearSession}
            disabled={isRunning}
            className="px-3 py-2 bg-dark-card border border-dark-border text-text-secondary rounded-lg text-sm hover:text-red-400 hover:border-red-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            title="Clear saved session and reset"
          >
            Clear
          </button>

          <button
            onClick={onExport}
            disabled={!hasMessages || isRunning}
            className="px-3 py-2 bg-dark-card border border-dark-border text-text-secondary rounded-lg text-sm hover:text-green-400 hover:border-green-400 transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            title="Copy conversation as markdown"
          >
            {exportStatus === 'copied' ? '✓ Copied' : exportStatus === 'downloaded' ? '✓ Downloaded' : 'Export'}
          </button>
        </div>
      </div>

      {/* Status text */}
      <div className="mt-3 text-xs text-text-secondary font-mono">
        {isRunning ? (
          <span>
            Round {currentRound} of {totalRounds}
            {currentAgentName && <span className="text-accent-amber"> — {currentAgentName} responding...</span>}
          </span>
        ) : canStart ? (
          'Ready to start'
        ) : (
          'Configure at least 2 agents with API keys'
        )}
      </div>
    </div>
  );
}
