/**
 * WattBot Agent Loop v0.3.0
 * Orchestrates: capture → LLM → parse → safety → execute → repeat
 * Supports tab management, debug logging, conversation history.
 * FIX: Capture retry limit with minimal fallback. Task framing prevents page description.
 */

(function() {
  "use strict";

  const MAX_HISTORY = 20;

  /**
   * Parse task text for conversation requirements.
   * Returns { required: number, topic: string } or null if not a conversation task.
   */
  function parseConversationReqs(taskText) {
    if (!taskText) return null;
    var lower = taskText.toLowerCase();

    // Look for explicit reply/message/exchange counts
    // Matches: "3-reply", "5 replies", "3 messages", "5 exchanges", "back and forth 3 times"
    var countPatterns = [
      /(\d+)[\s-]*(reply|replies|message|messages|exchange|exchanges|response|responses|turn|turns)/i,
      /(?:have|carry|hold|do)\s+(?:a\s+)?(\d+)[\s-]*(reply|message|exchange|turn|round)/i,
      /back\s+and\s+forth\s+(\d+)\s+time/i,
      /(\d+)\s+(?:back\s+and\s+forth|round)/i,
      /conversation\s+(?:of\s+)?(\d+)/i
    ];

    for (var i = 0; i < countPatterns.length; i++) {
      var match = taskText.match(countPatterns[i]);
      if (match) {
        var count = parseInt(match[1], 10);
        if (count > 0 && count <= 50) {
          return { required: count, topic: extractTopic(taskText) };
        }
      }
    }

    // Check for general conversation keywords WITHOUT a count
    // These indicate "have a conversation" but without specifying length
    var convKeywords = [
      "have a conversation", "carry on a conversation", "hold a conversation",
      "chat with", "talk to", "discuss with", "converse with",
      "back and forth", "keep talking", "continue the conversation"
    ];
    for (var j = 0; j < convKeywords.length; j++) {
      if (lower.indexOf(convKeywords[j]) !== -1) {
        // Default to 3 exchanges if no count specified
        return { required: 3, topic: extractTopic(taskText) };
      }
    }

    return null;
  }

  function extractTopic(text) {
    // Try to pull out "about X" topic
    var aboutMatch = text.match(/about\s+(.+?)(?:\.|$|\n)/i);
    return aboutMatch ? aboutMatch[1].trim() : "";
  }

  class WattBotAgent {
    constructor(adapter, options) {
      this.adapter = adapter;
      this.maxSteps = (options && options.maxSteps) || 100;
      this.useScreenshots = (options && options.useScreenshots) || false;
      this.onEvent = (options && options.onEvent) || function() {};
      this.conversation = [];
      this.stepCount = 0;
      this.running = false;
      this.paused = false;
      this.totalTokens = 0;
      this.totalCost = 0;
      this.debugLog = [];
      // Conversation enforcement state
      this.messagesSent = 0;
      this.convReqs = null; // { required, topic }
      this.doneRejections = 0;
    }

    log(type, data) {
      var entry = { time: Date.now(), type: type, data: data };
      this.debugLog.push(entry);
      if (this.debugLog.length > 200) this.debugLog.shift();
    }

    async run(task) {
      this.running = true;
      this.paused = false;
      this.stepCount = 0;
      this.conversation = [];
      this.debugLog = [];
      this.messagesSent = 0;
      this.doneRejections = 0;

      // Parse conversation requirements from the full task text
      this.convReqs = parseConversationReqs(task);
      if (this.convReqs) {
        this.log("conv_tracking", { required: this.convReqs.required, topic: this.convReqs.topic });
        this.onEvent("status", { message: "📊 Conversation mode: " + this.convReqs.required + " messages required" });
      }

      this.onEvent("started", { task: task });

      // Load system prompt
      var prompts;
      try {
        prompts = typeof SYSTEM_PROMPT !== "undefined"
          ? { SYSTEM_PROMPT: SYSTEM_PROMPT, buildPageState: buildPageState }
          : (typeof module !== "undefined" ? require("./prompts.js") : null);
      } catch (e) {
        // In extension context, these are global from script loading order
        prompts = { SYSTEM_PROMPT: SYSTEM_PROMPT, buildPageState: buildPageState };
      }

      this.conversation.push({ role: "user", content: "NEW TASK — Execute the following task. If the current page is not relevant to the task, navigate to the appropriate site first. Do NOT describe or summarize the current page unless the task asks you to. Only switch tabs if the task explicitly requires it.\n\nTask: " + task });

      while (this.running && this.stepCount < this.maxSteps) {
        // Check pause
        while (this.paused && this.running) {
          await new Promise(function(r) { setTimeout(r, 200); });
        }
        if (!this.running) break;

        try {
          this.stepCount++;
          this.onEvent("status", { step: this.stepCount, message: "Capturing page..." });

          // Capture page state (max 2 retries, then use minimal context)
          var capture = await this.sendMessage({ type: "CAPTURE_PAGE" });
          if (!capture || capture.error) {
            if (!this._captureFailCount) this._captureFailCount = 0;
            this._captureFailCount++;
            this.onEvent("error", { message: "Capture failed: " + (capture ? capture.error : "no response") });

            if (this._captureFailCount >= 2) {
              // Build minimal context from tab API so LLM can still navigate
              var fallbackTabs = await this.sendMessage({ type: "TAB_LIST" });
              var activeTab = (fallbackTabs && fallbackTabs.tabs || []).find(function(t) { return t.active; });
              capture = {
                url: activeTab ? activeTab.url : "unknown",
                title: activeTab ? activeTab.title : "unknown",
                pageText: "(Page content unavailable — content script could not connect. You can still navigate to another URL or switch tabs.)",
                interactiveElements: "",
                elementCount: 0,
                tabs: fallbackTabs ? fallbackTabs.tabs : []
              };
              this._captureFailCount = 0;
              this.onEvent("status", { step: this.stepCount, message: "Using minimal context..." });
            } else {
              await this.wait(2000);
              continue;
            }
          } else {
            this._captureFailCount = 0;
          }

          // Get tab list for context
          var tabData = await this.sendMessage({ type: "TAB_LIST" });
          if (tabData && tabData.tabs) {
            capture.tabs = tabData.tabs;
          }

          var pageState = prompts.buildPageState(capture, task);
          this.log("capture", { url: capture.url, elements: capture.elementCount, hasText: !!(capture.pageText || capture.text), tabs: (capture.tabs || []).length });

          // Optional screenshot
          var screenshot = null;
          if (this.useScreenshots) {
            try {
              var ssResult = await this.sendMessage({ type: "TAKE_SCREENSHOT" });
              if (ssResult && ssResult.screenshot) screenshot = ssResult.screenshot;
            } catch (e) { /* ignore screenshot errors */ }
          }

          // Build LLM message
          this.onEvent("status", { step: this.stepCount, message: "Thinking..." });
          var userMsg = pageState;

          // On first step, COMBINE task + page state (preserve the task context)
          // On subsequent steps, replace the previous page state
          if (this.stepCount === 1) {
            // Append page state to the existing task message
            for (var ci = this.conversation.length - 1; ci >= 0; ci--) {
              if (this.conversation[ci].role === "user") {
                this.conversation[ci].content = this.conversation[ci].content + "\n\n" + userMsg;
                break;
              }
            }
          } else {
            this.updateLastUserMessage(userMsg);
          }

          // Call LLM
          var llmResult = await this.adapter.sendMessage(prompts.SYSTEM_PROMPT, this.conversation, screenshot);
          this.log("llm_response", { raw: llmResult.text, tokens: llmResult.usage });

          this.totalTokens += (llmResult.usage && llmResult.usage.total) || 0;
          this.totalCost += (llmResult.usage && llmResult.usage.estimatedCost) || 0;

          // Parse response
          var parsed = parseAction(llmResult.text);
          this.log("parsed_action", parsed);

          if (parsed.error) {
            this.onEvent("error", { message: "Parse error: " + parsed.error });
            this.conversation.push({ role: "assistant", content: llmResult.text });
            this.conversation.push({ role: "user", content: "Your response was not valid JSON. Please output a single JSON action." });
            continue;
          }

          var action = parsed;
          this.conversation.push({ role: "assistant", content: JSON.stringify(action) });

          // Done action — with conversation enforcement gate
          if (action.action === "done") {
            // Check if conversation requirements are met
            if (this.convReqs && this.messagesSent < this.convReqs.required) {
              this.doneRejections++;
              this.log("done_rejected", { sent: this.messagesSent, required: this.convReqs.required, rejections: this.doneRejections });

              // Safety valve: if LLM keeps trying to quit, let it go after 3 rejections
              if (this.doneRejections >= 3) {
                this.log("done_forced", { reason: "3 rejections exceeded, allowing done" });
                this.onEvent("done", {
                  result: action.params.result + " (conversation incomplete: " + this.messagesSent + "/" + this.convReqs.required + " messages)",
                  steps: this.stepCount,
                  tokens: this.totalTokens,
                  cost: this.totalCost
                });
                this.running = false;
                break;
              }

              // Reject the done and tell the LLM to continue
              var remaining = this.convReqs.required - this.messagesSent;
              var feedback = "⚠️ CONVERSATION NOT COMPLETE. You have sent " + this.messagesSent + " of " + this.convReqs.required + " required messages. " +
                "You must send " + remaining + " more message" + (remaining > 1 ? "s" : "") + " before calling done. " +
                "Continue the conversation — read the latest response on the page and send your next message.";
              if (this.convReqs.topic) {
                feedback += " Keep the conversation about: " + this.convReqs.topic;
              }
              this.conversation.push({ role: "user", content: feedback });
              this.onEvent("status", { step: this.stepCount, message: "📊 " + this.messagesSent + "/" + this.convReqs.required + " messages — continuing..." });
              continue;
            }

            this.onEvent("done", {
              result: action.params.result,
              steps: this.stepCount,
              tokens: this.totalTokens,
              cost: this.totalCost
            });
            this.running = false;
            break;
          }

          // Navigate action — handled by service worker
          if (action.action === "navigate") {
            this.onEvent("action", { action: action });
            await this.sendMessage({ type: "NAVIGATE", url: action.params.url });
            this.conversation.push({ role: "user", content: "Navigated to " + action.params.url + ". Waiting for page load..." });
            await this.wait(2000);
            continue;
          }

          // Tab actions — handled by service worker
          if (action.action === "tab_open") {
            this.onEvent("action", { action: action });
            var tabResult = await this.sendMessage({ type: "TAB_OPEN", url: action.params.url, active: action.params.active });
            this.conversation.push({ role: "user", content: "Opened new tab" + (action.params.url ? ": " + action.params.url : "") + ". Tab ID: " + (tabResult.tabId || "unknown") });
            await this.wait(1500);
            continue;
          }

          if (action.action === "tab_switch") {
            this.onEvent("action", { action: action });
            var switchResult = await this.sendMessage({
              type: "TAB_SWITCH",
              tabId: action.params.tabId,
              index: action.params.index
            });
            if (switchResult.error) {
              this.conversation.push({ role: "user", content: "Tab switch failed: " + switchResult.error });
            } else {
              this.conversation.push({ role: "user", content: "Switched to tab: " + (switchResult.url || "unknown") });
            }
            await this.wait(1000);
            continue;
          }

          if (action.action === "tab_list") {
            this.onEvent("action", { action: action });
            var listResult = await this.sendMessage({ type: "TAB_LIST" });
            var tabInfo = (listResult.tabs || []).map(function(t) {
              return (t.active ? "→ " : "  ") + "[" + t.index + "] " + t.title + " (" + t.url + ")";
            }).join("\n");
            this.conversation.push({ role: "user", content: "Open tabs:\n" + tabInfo });
            continue;
          }

          if (action.action === "tab_close") {
            this.onEvent("action", { action: action });
            await this.sendMessage({ type: "TAB_CLOSE", tabId: action.params.tabId });
            this.conversation.push({ role: "user", content: "Tab closed." });
            await this.wait(500);
            continue;
          }

          // Safety check
          var safety = checkSafety(action, capture);
          this.log("safety_check", safety);

          if (safety.level === "block") {
            this.onEvent("blocked", { action: action, reason: safety.reason });
            this.conversation.push({ role: "user", content: "BLOCKED: " + safety.reason + ". Try a different approach." });
            continue;
          }

          if (safety.level === "confirm") {
            this.paused = true;
            this.onEvent("confirm_request", {
              action: action,
              reason: safety.reason,
              resolve: (function(approved) {
                this.paused = false;
                if (!approved) {
                  this.conversation.push({ role: "user", content: "User declined this action. Try a different approach." });
                }
                return approved;
              }).bind(this)
            });
            // Wait for user decision
            while (this.paused && this.running) {
              await new Promise(function(r) { setTimeout(r, 200); });
            }
            if (!this.running) break;
            continue;
          }

          // Execute action
          this.onEvent("action", { action: action });
          var result = await this.sendMessage({ type: "EXECUTE_ACTION", action: action });
          this.log("action_result", result);

          var feedback = "Action " + action.action + " completed.";
          if (result.error) feedback = "Action failed: " + result.error;
          else if (action.action === "type" && action.params.pressEnter) {
            // Track conversation messages sent
            if (this.convReqs) {
              this.messagesSent++;
              this.log("message_sent", { count: this.messagesSent, required: this.convReqs.required, text: action.params.text });
              feedback = "Typed \"" + action.params.text + "\" and pressed Enter — message sent. [Message " + this.messagesSent + " of " + this.convReqs.required + " sent]";
            } else {
              feedback = "Typed \"" + action.params.text + "\" and pressed Enter — message sent.";
            }
          } else if (result.actualText !== undefined) {
            feedback += " Text in field: \"" + result.actualText + "\"";
          }
          this.conversation.push({ role: "user", content: feedback });

          await this.wait(800);

        } catch (e) {
          this.log("error", e.message);
          this.onEvent("error", { message: e.message });
          await this.wait(1000);
        }

        // Trim history
        if (this.conversation.length > MAX_HISTORY * 2) {
          var keep = this.conversation.slice(0, 1);
          keep = keep.concat(this.conversation.slice(-MAX_HISTORY * 2));
          this.conversation = keep;
        }
      }

      if (this.stepCount >= this.maxSteps && this.running) {
        this.onEvent("error", { message: "Max steps (" + this.maxSteps + ") reached." });
      }
      this.running = false;
    }

    updateLastUserMessage(content) {
      // Replace the last user message with updated page state
      for (var i = this.conversation.length - 1; i >= 0; i--) {
        if (this.conversation[i].role === "user") {
          this.conversation[i].content = content;
          return;
        }
      }
      this.conversation.push({ role: "user", content: content });
    }

    sendMessage(msg) {
      return new Promise(function(resolve) {
        chrome.runtime.sendMessage(msg, function(response) {
          resolve(response || { error: "No response" });
        });
      });
    }

    wait(ms) {
      return new Promise(function(r) { setTimeout(r, ms); });
    }

    stop() { this.running = false; this.paused = false; }
    pause() { this.paused = true; }
    resume() { this.paused = false; }
    getDebugLog() { return this.debugLog; }
  }

  // Expose globally
  if (typeof window !== "undefined") window.WattBotAgent = WattBotAgent;
})();
