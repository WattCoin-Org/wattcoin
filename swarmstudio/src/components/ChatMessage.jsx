import { getAgentColor } from '../utils/colors';

export default function ChatMessage({ message, agentIndex, isStreaming }) {
  const agentColor = getAgentColor(agentIndex);

  return (
    <div className="flex gap-3 px-4 py-3 hover:bg-dark-panel/50 transition-colors">
      {/* Agent color dot */}
      <div 
        className="w-3 h-3 rounded-full flex-shrink-0 mt-1"
        style={{ backgroundColor: agentColor }}
      />

      {/* Message content */}
      <div className="flex-1 min-w-0">
        <div className="flex items-baseline gap-2 mb-1">
          <span className="text-sm font-medium text-text-primary">
            {message.agentName}
          </span>
          <span className="text-xs text-text-muted font-mono">
            Round {message.round}
          </span>
        </div>
        
        <div className={`text-sm text-text-secondary leading-relaxed ${message.error ? 'text-red-400 italic' : ''}`}>
          {message.content}
          {isStreaming && (
            <span className="inline-block w-2 h-4 ml-1 bg-accent-amber animate-pulse" />
          )}
        </div>
      </div>
    </div>
  );
}
