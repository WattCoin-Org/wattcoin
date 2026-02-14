# WattBot Changelog

## v0.3.1 — February 13, 2026

### Fixes
- Added drag handle above input area — drag up/down to resize both task and prompt textareas
- Removed broken CSS resize handles from both textareas
- Task input is now resizable again (was locked at `resize: none` with no alternative)
- Prompt textarea max-height limit removed

## v0.3.0 — February 13, 2026

### New Features
- **Tasks Quick Action**: ⚡ Tasks button navigates to task marketplace and lists open tasks with rewards
- **WSI Quick Action**: ⚡ WSI button navigates to distributed inference network status page
- **Blinks Quick Action**: ⚡ Blinks button navigates to Solana Blinks/Actions page with available actions

### Visual Overhaul — SwarmStudio Design System
- **Color system**: Pure dark palette (#0D0D0D bg, #1A1A1A panels, #262626 cards) replacing GitHub-dark theme
- **Typography**: Inter + JetBrains Mono font pairing (loaded via Google Fonts)
- **Chat bubbles**: Rounded 12px cards with subtle gradient backgrounds per message type
- **Action messages**: Blue left-border accent with monospace action type labels
- **Success/error/warning messages**: Gradient tinted backgrounds with colored borders
- **Quick action pills**: Rounded 16px pill buttons with hover lift effect
- **Input area**: Cleaner 10px radius inputs with amber focus ring
- **Run button**: Amber-to-orange gradient matching SwarmStudio accent
- **Confirm dialog**: Frosted glass overlay with 16px rounded card
- **History items**: Hover glow with amber tint
- **Scrollbars**: Minimal 4px width, dark track
- **Animations**: Slide-in for new messages, pulse-amber for thinking state
- **Settings page**: Color variables aligned with sidepanel (consistent dark theme)

### Technical
- All extension source files now committed to repo (manifest, service-worker, content scripts, adapters, core modules — previously only in zip builds)
- Source published to public repo for transparency
- Version bumped across all files (manifest, service-worker, agent, prompts, settings)

## v0.2.0 — February 9, 2026

### New Features
- **Smart Model Selection**: Custom model text input overrides dropdown — type any model string for new or unlisted models
- **Refresh Models**: Button fetches available models from provider's /models API endpoint
- **WattCoin Quick Actions**: Second row of gold-accent buttons — Bounties (GitHub issues), SwarmSolve (navigate), Balance (live fetch)
- **Live Balance Fetch**: ⚡ Balance button queries Solana RPC for WATT + SOL balance, displays inline with Solscan link
- **Wallet Helper Module**: `wallet-helper.js` — detect Phantom, connect/disconnect, getWattBalance, getSolBalance, signMessage
- **Wallet Status Indicator**: Green dot in header when wallet connected, status display in settings
- **Manual Wallet Address**: Settings input for non-Phantom users to paste their Solana address
- **Improved Test Connection**: Now actually calls chat/completions (not just /models) for real validation

### Technical
- `sidepanel/wallet-helper.js` (new) — high-level wallet API wrapping chrome.tabs.sendMessage to wallet bridge
- Settings saves `customModel` and `walletAddress` to chrome.storage.sync
- Balance uses `getTokenAccountsByOwner` RPC with WATT mint address
- Wallet indicator listens for `chrome.storage.onChanged` events

## v0.1.3 — February 9, 2026

### Bug Fixes
- **Critical**: Fixed agent loop bug where task instructions were overwritten by page state on first step
- Task preservation: original task now locked in conversation history, never replaced
- Tab drift prevention: agent stays on the tab it started on
- Conversation enforcement: multi-step conversations now complete reliably

## v0.1.2 — February 9, 2026

### Features
- Quick action buttons: Summarize, Emails, Links, Fill Form
- Chat history with task replay
- Debug console with real-time log
- System prompt section (collapsible)
- Hover, keypress, copy, tab actions added
- Pause/resume support

### Bug Fixes
- Fixed LLM blind to page elements (field name mismatch)
- Fixed contenteditable typing for rich text editors (ProseMirror/Slate)
- Fixed adapter constructor issues
- Fixed global function scoping

## v0.1.0 — February 9, 2026

### Initial Release
- Chrome MV3 extension with sidepanel UI
- DOM capture → LLM call → action execution loop
- OpenAI and Anthropic adapters
- Safety system: domain blocking, action confirmation, step limits
- Settings page with provider/model configuration
- Content scripts for DOM interaction and highlighting

