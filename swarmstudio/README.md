# SwarmStudio

Multi-LLM conversation orchestrator - coordinate conversations between multiple AI models.

## Features

- **7 Providers Supported**: OpenAI, Anthropic, xAI (Grok), Google (Gemini), DeepSeek, Custom endpoints
- **Dark Theme**: Professional UI with WattCoin amber/orange branding
- **Agent Configuration**: Up to 6 agents with individual provider/model/API key settings
- **Cost Tracking**: Real-time token usage and cost estimation per model
- **System Prompts**: Customize each agent's behavior

## Quick Start

```bash
# Install dependencies
npm install

# Start development server
npm run dev

# Build for production
npm run build
```

## Configuration

Create a `.env` file:

```
VITE_API_URL=https://wattcoin.org
```

## Supported Providers

### Active
- **OpenAI** - GPT-4o, GPT-4o-mini, O-series models
- **Anthropic** - Claude Sonnet 4, Opus 4.5, Haiku 4.5
- **xAI** - Grok-3, Grok-3-fast, Grok-3-mini
- **Google** - Gemini 2.5 Pro/Flash, Gemini 2.0 Flash
- **DeepSeek** - DeepSeek Chat, DeepSeek Reasoner
- **Custom** - Any OpenAI-compatible endpoint (LM Studio, vLLM, etc.)

### Coming Soon
- **Ollama** - Local models (desktop version)
- **WSI** - WattCoin SuperIntelligence

## Architecture

```
swarmstudio/
├── src/
│   ├── components/      # React components
│   ├── config/          # Provider registry & pricing
│   ├── hooks/           # React hooks (streaming fetch)
│   ├── utils/           # API client, color palette
│   └── styles/          # Tailwind CSS
├── public/              # Static assets
└── package.json
```

## Tech Stack

- **React** 18.3 - UI framework
- **Vite** 5.4 - Build tool
- **Tailwind CSS** 3.4 - Styling

## License

Private - WattCoin-Org
