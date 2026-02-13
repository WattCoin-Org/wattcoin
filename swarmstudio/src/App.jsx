import { useState, useEffect, useCallback } from 'react';
import AgentPanel from './components/AgentPanel';
import ControlBar from './components/ControlBar';
import ChatWindow from './components/ChatWindow';
import CostTracker from './components/CostTracker';
import { useConversation } from './hooks/useConversation';

const STORAGE_KEY = 'swarmstudio_session';

function createDefaultAgent(id, name, provider, model) {
  return {
    id,
    name,
    provider,
    model,
    customModel: '',
    baseUrl: '',
    apiKey: '',
    systemPrompt: '',
    status: 'idle'
  };
}

function loadSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (data.agents && Array.isArray(data.agents) && data.agents.length >= 2) {
      return data;
    }
  } catch (e) {
    console.warn('Failed to load session:', e);
  }
  return null;
}

export default function App() {
  const saved = loadSession();

  const [agents, setAgents] = useState(
    saved?.agents || [
      createDefaultAgent(1, 'Agent 1', 'openai', 'gpt-4o'),
      createDefaultAgent(2, 'Agent 2', 'anthropic', 'claude-sonnet-4-20250514'),
    ]
  );

  const [prompt, setPrompt] = useState(saved?.prompt || '');
  const [rounds, setRounds] = useState(saved?.rounds || 3);
  const [sessionSaved, setSessionSaved] = useState(!!saved);

  // Conversation engine
  const {
    messages,
    isRunning,
    currentAgent,
    currentRound,
    usage,
    startConversation,
    stopConversation
  } = useConversation();

  const handleSaveSession = useCallback(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ agents, prompt, rounds }));
      setSessionSaved(true);
      setTimeout(() => setSessionSaved(false), 2000);
    } catch (e) {
      console.error('Failed to save session:', e);
    }
  }, [agents, prompt, rounds]);

  const handleClearSession = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
    setAgents([
      createDefaultAgent(1, 'Agent 1', 'openai', 'gpt-4o'),
      createDefaultAgent(2, 'Agent 2', 'anthropic', 'claude-sonnet-4-20250514'),
    ]);
    setPrompt('');
    setRounds(3);
  }, []);

  const [exportStatus, setExportStatus] = useState('');

  const handleExportConversation = useCallback(() => {
    if (!messages.length) return;

    let md = `# SwarmStudio Conversation\n\n`;
    md += `**Prompt:** ${prompt}\n\n`;
    md += `**Agents:** ${agents.filter(a => a.apiKey).map(a => `${a.name} (${a.provider}/${a.customModel || a.model})`).join(', ')}\n\n`;
    md += `---\n\n`;

    let lastRound = 0;
    for (const msg of messages) {
      if (msg.round !== lastRound) {
        lastRound = msg.round;
        md += `## Round ${msg.round}\n\n`;
      }
      md += `### ${msg.agentName}\n\n${msg.content}\n\n`;
    }

    // Copy to clipboard
    navigator.clipboard.writeText(md).then(() => {
      setExportStatus('copied');
      setTimeout(() => setExportStatus(''), 2000);
    }).catch(() => {
      // Fallback: download as file
      const blob = new Blob([md], { type: 'text/markdown' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `swarmstudio-${new Date().toISOString().slice(0,10)}.md`;
      a.click();
      URL.revokeObjectURL(url);
      setExportStatus('downloaded');
      setTimeout(() => setExportStatus(''), 2000);
    });
  }, [messages, prompt, agents]);

  const handleUpdateAgent = (id, updates) => {
    setAgents(agents.map(agent => 
      agent.id === id ? { ...agent, ...updates } : agent
    ));
  };

  const handleAddAgent = () => {
    if (agents.length >= 6) return;
    
    const newId = Math.max(...agents.map(a => a.id)) + 1;
    const newAgent = createDefaultAgent(
      newId, 
      `Agent ${newId}`, 
      'openai', 
      'gpt-4o-mini'
    );
    setAgents([...agents, newAgent]);
  };

  const handleDeleteAgent = (id) => {
    if (agents.length <= 2) return;
    setAgents(agents.filter(agent => agent.id !== id));
  };

  const handleStart = () => {
    if (!canStart) return;
    startConversation(agents, prompt, rounds);
  };

  const handleStop = () => {
    stopConversation();
  };

  // Check if at least 2 agents have API keys
  const agentsWithKeys = agents.filter(a => a.apiKey && a.apiKey.trim()).length;
  const canStart = agentsWithKeys >= 2 && prompt.trim() && !isRunning;

  // Get current agent name for status display
  const currentAgentName = currentAgent 
    ? agents.find(a => a.id === currentAgent)?.name 
    : null;

  return (
    <div className="h-screen flex flex-col bg-dark-bg">
      <ControlBar
        prompt={prompt}
        rounds={rounds}
        onPromptChange={setPrompt}
        onRoundsChange={setRounds}
        onStart={handleStart}
        onStop={handleStop}
        canStart={canStart}
        isRunning={isRunning}
        currentRound={currentRound}
        totalRounds={rounds}
        currentAgentName={currentAgentName}
        onSaveSession={handleSaveSession}
        onClearSession={handleClearSession}
        sessionSaved={sessionSaved}
        onExport={handleExportConversation}
        exportStatus={exportStatus}
        hasMessages={messages.length > 0}
      />

      <div className="flex-1 flex overflow-hidden">
        <AgentPanel
          agents={agents}
          onUpdateAgent={handleUpdateAgent}
          onAddAgent={handleAddAgent}
          onDeleteAgent={handleDeleteAgent}
        />

        <ChatWindow
          messages={messages}
          currentAgent={currentAgent}
          currentRound={currentRound}
          totalRounds={rounds}
          agents={agents}
        />
      </div>

      <CostTracker
        agents={agents}
        usage={usage}
      />
    </div>
  );
}
