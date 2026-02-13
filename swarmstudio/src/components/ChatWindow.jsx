import { useEffect, useRef, useState } from 'react';
import ChatMessage from './ChatMessage';

export default function ChatWindow({ messages, currentAgent, currentRound, totalRounds, agents }) {
  const messagesEndRef = useRef(null);
  const containerRef = useRef(null);
  const [userScrolledUp, setUserScrolledUp] = useState(false);

  // Detect if user scrolled away from bottom
  const handleScroll = () => {
    const el = containerRef.current;
    if (!el) return;
    const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight;
    setUserScrolledUp(distanceFromBottom > 80);
  };

  // Auto-scroll only if user hasn't scrolled up
  useEffect(() => {
    if (!userScrolledUp) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [messages, userScrolledUp]);

  if (messages.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center space-y-4 max-w-md">
          <div className="w-16 h-16 mx-auto gradient-accent rounded-full opacity-20 flex items-center justify-center">
            <svg className="w-8 h-8 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
            </svg>
          </div>
          <div>
            <h3 className="text-lg font-medium mb-2">Configure Your Agents</h3>
            <p className="text-sm text-text-secondary">
              Set up at least 2 agents with valid API keys, then start a conversation using the control bar above.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Round indicator */}
      {currentRound > 0 && totalRounds > 0 && (
        <div className="px-4 py-2 bg-dark-panel border-b border-dark-border">
          <div className="text-xs font-mono text-text-secondary">
            Round {currentRound} of {totalRounds}
          </div>
        </div>
      )}

      {/* Messages */}
      <div className="flex-1 overflow-y-auto" ref={containerRef} onScroll={handleScroll}>
        <div className="py-4 space-y-1">
          {messages.map((message, index) => {
            const agentIndex = agents.findIndex(a => a.id === message.agentId);
            const isStreaming = currentAgent === message.agentId && index === messages.length - 1;
            
            return (
              <ChatMessage
                key={message.id}
                message={message}
                agentIndex={agentIndex}
                isStreaming={isStreaming}
              />
            );
          })}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* Scroll to bottom button when scrolled up */}
      {userScrolledUp && messages.length > 0 && (
        <button
          onClick={() => {
            setUserScrolledUp(false);
            messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
          }}
          className="absolute bottom-20 right-8 px-3 py-1.5 bg-dark-card border border-dark-border rounded-full text-xs text-text-secondary hover:text-accent-amber hover:border-accent-amber transition-colors shadow-lg"
        >
          ↓ Scroll to bottom
        </button>
      )}
    </div>
  );
}
