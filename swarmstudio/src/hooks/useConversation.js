import { useState, useCallback, useRef } from 'react';
import { streamChat } from '../utils/api';

export function useConversation() {
  const [messages, setMessages] = useState([]);
  const [isRunning, setIsRunning] = useState(false);
  const [currentAgent, setCurrentAgent] = useState(null);
  const [currentRound, setCurrentRound] = useState(0);
  const [usage, setUsage] = useState({});
  
  const cancelledRef = useRef(false);
  const currentMessageRef = useRef('');

  const stopConversation = useCallback(() => {
    cancelledRef.current = true;
  }, []);

  const startConversation = useCallback(async (agents, initialPrompt, totalRounds) => {
    // Reset state
    setMessages([]);
    setIsRunning(true);
    setCurrentRound(1);
    cancelledRef.current = false;
    
    // Initialize usage tracking for all agents
    const initialUsage = {};
    agents.forEach(agent => {
      initialUsage[agent.id] = { inputTokens: 0, outputTokens: 0 };
    });
    setUsage(initialUsage);

    // Conversation history (shared across all agents)
    const conversationHistory = [];

    try {
      for (let round = 1; round <= totalRounds; round++) {
        if (cancelledRef.current) break;
        
        setCurrentRound(round);

        for (let agentIndex = 0; agentIndex < agents.length; agentIndex++) {
          if (cancelledRef.current) break;

          const agent = agents[agentIndex];
          setCurrentAgent(agent.id);

          // Build messages for this agent
          const agentMessages = [];
          
          // System prompt
          if (agent.systemPrompt) {
            agentMessages.push({
              role: 'system',
              content: agent.systemPrompt
            });
          }

          // Original user prompt (only in round 1, first agent)
          if (round === 1 && agentIndex === 0) {
            agentMessages.push({
              role: 'user',
              content: initialPrompt
            });
          } else {
            // Add conversation history as context
            // Other agents' messages appear as "user" role
            // This agent's own messages appear as "assistant" role
            conversationHistory.forEach(msg => {
              if (msg.agentId === agent.id) {
                // This agent's own previous messages
                agentMessages.push({
                  role: 'assistant',
                  content: msg.content
                });
              } else {
                // Other agents' messages (labeled)
                agentMessages.push({
                  role: 'user',
                  content: `${msg.agentName} said: ${msg.content}`
                });
              }
            });

            // Prompt for this turn
            agentMessages.push({
              role: 'user',
              content: "It's your turn to respond."
            });
          }

          // Create message object
          const messageId = `msg_${Date.now()}_${agent.id}_${round}`;
          const newMessage = {
            id: messageId,
            agentId: agent.id,
            agentName: agent.name,
            content: '',
            role: 'assistant',
            round: round
          };

          // Add to UI immediately
          setMessages(prev => [...prev, newMessage]);
          currentMessageRef.current = '';

          // Stream response
          let streamComplete = false;
          let streamError = null;

          await streamChat(
            agent.provider,
            agent.customModel || agent.model,
            agent.apiKey,
            agent.baseUrl || '',
            agentMessages,
            4096,
            // onToken
            (token) => {
              currentMessageRef.current += token;
              setMessages(prev => prev.map(m => 
                m.id === messageId 
                  ? { ...m, content: currentMessageRef.current }
                  : m
              ));
            },
            // onUsage
            (inputTokens, outputTokens) => {
              setUsage(prev => ({
                ...prev,
                [agent.id]: {
                  inputTokens: (prev[agent.id]?.inputTokens || 0) + inputTokens,
                  outputTokens: (prev[agent.id]?.outputTokens || 0) + outputTokens
                }
              }));
            },
            // onDone
            () => {
              streamComplete = true;
            },
            // onError
            (error) => {
              streamError = error;
              streamComplete = true;
            }
          );

          // Add completed message to history
          if (!streamError) {
            conversationHistory.push({
              ...newMessage,
              content: currentMessageRef.current
            });
          } else {
            // Show error in chat
            const errorContent = `[Error: ${streamError}]`;
            setMessages(prev => prev.map(m => 
              m.id === messageId 
                ? { ...m, content: errorContent, error: true }
                : m
            ));
            // Skip this agent but continue with others
          }

          // Brief pause between agents
          await new Promise(resolve => setTimeout(resolve, 500));
        }

        // Brief pause between rounds
        if (round < totalRounds) {
          await new Promise(resolve => setTimeout(resolve, 1000));
        }
      }
    } finally {
      setIsRunning(false);
      setCurrentAgent(null);
      setCurrentRound(0);
      cancelledRef.current = false;
    }
  }, []);

  return {
    messages,
    isRunning,
    currentAgent,
    currentRound,
    usage,
    startConversation,
    stopConversation
  };
}
