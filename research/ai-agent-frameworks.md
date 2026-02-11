# AI Agent Frameworks Integration Analysis (Issue #146)

Generated from GitHub API metadata, sorted by GitHub stars descending.

## Summary Table

| Rank | Framework | GitHub | Stars | Language | License | WATT Integration Potential |
|---:|---|---|---:|---|---|---|
| 1 | OpenClaw | [openclaw/openclaw](https://github.com/openclaw/openclaw) | 184649 | TypeScript | MIT | High |
| 2 | AutoGPT | [Significant-Gravitas/AutoGPT](https://github.com/Significant-Gravitas/AutoGPT) | 181787 | Python | NOASSERTION | Medium |
| 3 | LangChain Agents | [langchain-ai/langchain](https://github.com/langchain-ai/langchain) | 126480 | Python | MIT | High |
| 4 | MetaGPT | [geekan/MetaGPT](https://github.com/FoundationAgents/MetaGPT) | 64118 | Python | MIT | High |
| 5 | Open Interpreter | [OpenInterpreter/open-interpreter](https://github.com/openinterpreter/open-interpreter) | 62110 | Python | AGPL-3.0 | Medium |
| 6 | Microsoft AutoGen | [microsoft/autogen](https://github.com/microsoft/autogen) | 54484 | Python | CC-BY-4.0 | High |
| 7 | LlamaIndex Workflows | [run-llama/llama_index](https://github.com/run-llama/llama_index) | 46939 | Python | MIT | High |
| 8 | CrewAI | [crewAIInc/crewAI](https://github.com/crewAIInc/crewAI) | 43977 | Python | MIT | High |
| 9 | LiteLLM | [BerriAI/litellm](https://github.com/BerriAI/litellm) | 35756 | Python | NOASSERTION | High |
| 10 | AgentGPT | [reworkd/AgentGPT](https://github.com/reworkd/AgentGPT) | 35702 | TypeScript | GPL-3.0 | Medium |
| 11 | DSPy | [stanfordnlp/dspy](https://github.com/stanfordnlp/dspy) | 32136 | Python | MIT | Medium |
| 12 | ChatDev | [OpenBMB/ChatDev](https://github.com/OpenBMB/ChatDev) | 30850 | Python | Apache-2.0 | Medium |
| 13 | smolagents | [huggingface/smolagents](https://github.com/huggingface/smolagents) | 25401 | Python | Apache-2.0 | Medium |
| 14 | LangGraph | [langchain-ai/langgraph](https://github.com/langchain-ai/langgraph) | 24602 | Python | MIT | High |
| 15 | Haystack Agents | [deepset-ai/haystack](https://github.com/deepset-ai/haystack) | 24165 | MDX | Apache-2.0 | Medium |
| 16 | BabyAGI | [yoheinakajima/babyagi](https://github.com/yoheinakajima/babyagi) | 22137 | Python | Unknown | Medium |
| 17 | Mastra | [mastra-ai/mastra](https://github.com/mastra-ai/mastra) | 20987 | TypeScript | NOASSERTION | Medium |
| 18 | ElizaOS | [elizaOS/eliza](https://github.com/elizaOS/eliza) | 17511 | TypeScript | MIT | Medium |
| 19 | CAMEL | [camel-ai/camel](https://github.com/camel-ai/camel) | 16006 | Python | Apache-2.0 | Medium |
| 20 | PydanticAI | [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai) | 14823 | Python | MIT | High |

## Per-Framework Notes

### OpenClaw
- GitHub: https://github.com/openclaw/openclaw
- Stars: 184649
- Primary language: TypeScript
- License: MIT
- Description: Your own personal AI assistant. Any OS. Any Platform. The lobster way. 🦞
- Key features: tool_use, multi-agent, skills, automation
- WATT integration potential: High
- Reasoning: Aligned with autonomous task execution and bounty workflows; low adaptation overhead for WATT-based payments.

### AutoGPT
- GitHub: https://github.com/Significant-Gravitas/AutoGPT
- Stars: 181787
- Primary language: Python
- License: NOASSERTION
- Description: AutoGPT is the vision of accessible AI for everyone, to use and to build on. Our mission is to provide the tools, so that you can focus on what matters.
- Key features: autonomous_agents, tool_use, task_planning, memory
- WATT integration potential: Medium
- Reasoning: Broad autonomy support but usually needs tighter guardrails for production payment-linked actions.

### LangChain Agents
- GitHub: https://github.com/langchain-ai/langchain
- Stars: 126480
- Primary language: Python
- License: MIT
- Description: 🦜🔗 The platform for reliable agents.
- Key features: tool_use, memory, retrieval, agent_orchestration
- WATT integration potential: High
- Reasoning: Mature tool-calling and retrieval stack makes it straightforward to wrap WATT APIs as agent tools.

### MetaGPT
- GitHub: https://github.com/FoundationAgents/MetaGPT
- Stars: 64118
- Primary language: Python
- License: MIT
- Description: 🌟 The Multi-Agent Framework: First AI Software Company, Towards Natural Language Programming
- Key features: multi-agent, role_based_agents, software_delivery, planning
- WATT integration potential: High
- Reasoning: Software-delivery focused agent roles fit WATT bounty and repo-targeted execution patterns.

### Open Interpreter
- GitHub: https://github.com/openinterpreter/open-interpreter
- Stars: 62110
- Primary language: Python
- License: AGPL-3.0
- Description: A natural language interface for computers
- Key features: local_execution, tool_use, code_actions, automation
- WATT integration potential: Medium
- Reasoning: Powerful automation surface, but local execution permissions require strict sandbox policy.

### Microsoft AutoGen
- GitHub: https://github.com/microsoft/autogen
- Stars: 54484
- Primary language: Python
- License: CC-BY-4.0
- Description: A programming framework for agentic AI
- Key features: multi-agent, tool_use, group_chat, orchestration
- WATT integration potential: High
- Reasoning: Strong multi-agent orchestration maps directly to SwarmSolve-style claim/review/ship loops.

### LlamaIndex Workflows
- GitHub: https://github.com/run-llama/llama_index
- Stars: 46939
- Primary language: Python
- License: MIT
- Description: LlamaIndex is the leading framework for building LLM-powered agents over your data.
- Key features: retrieval, agentic_workflows, tool_use, data_connectors
- WATT integration potential: High
- Reasoning: Data-connected workflows can integrate WATT services and telemetry with minimal glue code.

### CrewAI
- GitHub: https://github.com/crewAIInc/crewAI
- Stars: 43977
- Primary language: Python
- License: MIT
- Description: Framework for orchestrating role-playing, autonomous AI agents. By fostering collaborative intelligence, CrewAI empowers agents to work together seamlessly, tackling complex tasks.
- Key features: multi-agent, task_flows, tool_use, planning
- WATT integration potential: High
- Reasoning: Task/crew abstractions are practical for structured paid task routing and execution auditing.

### LiteLLM
- GitHub: https://github.com/BerriAI/litellm
- Stars: 35756
- Primary language: Python
- License: NOASSERTION
- Description: Python SDK, Proxy Server (AI Gateway) to call 100+ LLM APIs in OpenAI (or native) format, with cost tracking, guardrails, loadbalancing and logging. [Bedrock, Azure, OpenAI, VertexAI, Cohere, Anthropic, Sagemaker, HuggingFace, VLLM, NVIDIA NIM]
- Key features: model_routing, provider_abstraction, budget_controls, observability
- WATT integration potential: High
- Reasoning: Useful LLM gateway for WATT services with routing, limits, and provider flexibility.

### AgentGPT
- GitHub: https://github.com/reworkd/AgentGPT
- Stars: 35702
- Primary language: TypeScript
- License: GPL-3.0
- Description: 🤖 Assemble, configure, and deploy autonomous AI Agents in your browser.
- Key features: web_ui, autonomous_agents, goal_decomposition, browser_exec
- WATT integration potential: Medium
- Reasoning: Good operator UX; backend hardening is still needed for financial-grade automation.

### DSPy
- GitHub: https://github.com/stanfordnlp/dspy
- Stars: 32136
- Primary language: Python
- License: MIT
- Description: DSPy: The framework for programming—not prompting—language models
- Key features: programmatic_prompting, optimizer, evaluation, composable_modules
- WATT integration potential: Medium
- Reasoning: Excellent optimization/eval layer; integration value is highest around existing execution frameworks.

### ChatDev
- GitHub: https://github.com/OpenBMB/ChatDev
- Stars: 30850
- Primary language: Python
- License: Apache-2.0
- Description: ChatDev 2.0: Dev All through LLM-powered Multi-Agent Collaboration
- Key features: multi-agent, software_company_sim, code_generation, planning
- WATT integration potential: Medium
- Reasoning: Interesting collaboration model; practical integration requires workflow simplification.

### smolagents
- GitHub: https://github.com/huggingface/smolagents
- Stars: 25401
- Primary language: Python
- License: Apache-2.0
- Description: 🤗 smolagents: a barebones library for agents that think in code.
- Key features: tool_use, code_agents, lightweight, hub_integration
- WATT integration potential: Medium
- Reasoning: Fast for prototyping WATT tools; larger production orchestration needs extra infra.

### LangGraph
- GitHub: https://github.com/langchain-ai/langgraph
- Stars: 24602
- Primary language: Python
- License: MIT
- Description: Build resilient language agents as graphs.
- Key features: stateful_graphs, tool_use, human_in_loop, durable_execution
- WATT integration potential: High
- Reasoning: Durable graph state and human-in-the-loop controls suit escrow and payout-sensitive pipelines.

### Haystack Agents
- GitHub: https://github.com/deepset-ai/haystack
- Stars: 24165
- Primary language: MDX
- License: Apache-2.0
- Description: AI orchestration framework to build customizable, production-ready LLM applications. Connect components (models, vector DBs, file converters) to pipelines or agents that can interact with your data. With advanced retrieval methods, it's best suited for building RAG, question answering, semantic search or conversational agent chatbots.
- Key features: retrieval, pipelines, tool_use, evaluation
- WATT integration potential: Medium
- Reasoning: Strong enterprise retrieval tooling; direct marketplace automation needs extra task-state plumbing.

### BabyAGI
- GitHub: https://github.com/yoheinakajima/babyagi
- Stars: 22137
- Primary language: Python
- License: Unknown
- Description: 
- Key features: task_management, memory, planning, autonomous_loop
- WATT integration potential: Medium
- Reasoning: Useful lightweight planner; needs external reliability and policy layers for WATT operations.

### Mastra
- GitHub: https://github.com/mastra-ai/mastra
- Stars: 20987
- Primary language: TypeScript
- License: NOASSERTION
- Description: From the team behind Gatsby, Mastra is a framework for building AI-powered applications and agents with a modern TypeScript stack.
- Key features: agent_framework, workflows, integrations, tool_use
- WATT integration potential: Medium
- Reasoning: Good workflow primitives, though ecosystem depth is still growing.

### ElizaOS
- GitHub: https://github.com/elizaOS/eliza
- Stars: 17511
- Primary language: TypeScript
- License: MIT
- Description: Autonomous agents for everyone
- Key features: agent_runtime, plugin_system, social_integrations, memory
- WATT integration potential: Medium
- Reasoning: Plugin ecosystem helps distribution, but primary focus is social-agent runtime.

### CAMEL
- GitHub: https://github.com/camel-ai/camel
- Stars: 16006
- Primary language: Python
- License: Apache-2.0
- Description: 🐫 CAMEL: The first and the best multi-agent framework. Finding the Scaling Law of Agents. https://www.camel-ai.org
- Key features: multi-agent, role_play, simulation, society_of_agents
- WATT integration potential: Medium
- Reasoning: Strong multi-agent research patterns; production integration usually needs custom controls.

### PydanticAI
- GitHub: https://github.com/pydantic/pydantic-ai
- Stars: 14823
- Primary language: Python
- License: MIT
- Description: GenAI Agent Framework, the Pydantic way
- Key features: typed_agents, tool_use, validation, python_ecosystem
- WATT integration potential: High
- Reasoning: Typed tool interfaces reduce runtime risk in payment and bounty automation paths.

---

**Payout Wallet**: same wallet as prior approved payouts for `@hriszc` (can be posted explicitly in follow-up comment if required by maintainer checks).