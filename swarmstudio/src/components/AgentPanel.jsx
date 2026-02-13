import AgentCard from './AgentCard';
import { getAgentColor } from '../utils/colors';

export default function AgentPanel({ agents, onUpdateAgent, onAddAgent, onDeleteAgent }) {
  const canAddMore = agents.length < 6;
  const canDelete = agents.length > 2;

  return (
    <div className="w-80 h-full bg-dark-panel border-r border-dark-border flex flex-col">
      {/* Header */}
      <div className="px-4 py-4 border-b border-dark-border">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-mono font-semibold">Agents</h2>
          <span className="px-2 py-0.5 bg-dark-card rounded text-xs text-text-secondary">
            {agents.length}
          </span>
        </div>
      </div>

      {/* Agent list */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {agents.map((agent, index) => (
          <AgentCard
            key={agent.id}
            agent={agent}
            color={getAgentColor(index)}
            onUpdate={(updates) => onUpdateAgent(agent.id, updates)}
            onDelete={() => onDeleteAgent(agent.id)}
            canDelete={canDelete}
          />
        ))}
      </div>

      {/* Add button */}
      <div className="p-4 border-t border-dark-border">
        <button
          onClick={onAddAgent}
          disabled={!canAddMore}
          className="w-full px-4 py-3 gradient-accent text-white rounded-lg font-medium hover:opacity-90 transition-opacity disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
        >
          <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          Add Agent
          {!canAddMore && <span className="text-xs opacity-75">(Max 6)</span>}
        </button>
      </div>
    </div>
  );
}
