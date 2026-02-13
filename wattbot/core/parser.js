/**
 * WattBot Response Parser
 * Parses LLM text responses into structured action objects.
 */

/**
 * Parse LLM response text into an action object.
 * Expected format: {"action": "click", "params": {"id": "wb-003"}, "reasoning": "..."}
 * Also handles common LLM quirks (markdown code blocks, extra text, etc.)
 * 
 * @param {string} text - Raw LLM response
 * @returns {object} Parsed action or error
 */
function parseResponse(text) {
  if (!text || typeof text !== "string") {
    return { error: "Empty response from LLM" };
  }
  
  // Try to extract JSON from response
  let jsonStr = text.trim();
  
  // Strip markdown code blocks if present
  const codeBlockMatch = jsonStr.match(/```(?:json)?\s*\n?([\s\S]*?)\n?\s*```/);
  if (codeBlockMatch) {
    jsonStr = codeBlockMatch[1].trim();
  }
  
  // Try to find JSON object in the text
  const jsonMatch = jsonStr.match(/\{[\s\S]*\}/);
  if (jsonMatch) {
    jsonStr = jsonMatch[0];
  }
  
  try {
    const parsed = JSON.parse(jsonStr);
    
    // Validate required fields
    if (!parsed.action) {
      return { error: "Response missing 'action' field", raw: text };
    }
    
    // Normalize action structure
    const action = {
      action: parsed.action.toLowerCase(),
      params: parsed.params || {},
      reasoning: parsed.reasoning || parsed.thought || ""
    };
    
    // Validate action-specific params
    const validation = validateAction(action);
    if (validation) {
      return { error: validation, raw: text };
    }
    
    return action;
    
  } catch (e) {
    // If JSON parse fails, try to interpret as natural language
    return parseFreeform(text);
  }
}

/**
 * Validate action has required params.
 */
function validateAction(action) {
  switch (action.action) {
    case "click":
      if (!action.params.id) return "Click action requires 'id' param";
      break;
    case "type":
      if (!action.params.id) return "Type action requires 'id' param";
      if (action.params.text === undefined) return "Type action requires 'text' param";
      break;
    case "select":
      if (!action.params.id) return "Select action requires 'id' param";
      if (!action.params.value) return "Select action requires 'value' param";
      break;
    case "navigate":
      if (!action.params.url) return "Navigate action requires 'url' param";
      break;
    case "scroll":
      // direction is optional, defaults to "down"
      break;
    case "wait":
      // ms is optional, defaults to 1000
      break;
    case "extract":
      // selector is optional
      break;
    case "done":
      // result/summary in params or reasoning
      break;
    case "hover":
      if (!action.params.id) return "Hover action requires 'id' param";
      break;
    case "keypress":
      if (!action.params.key) return "Keypress action requires 'key' param";
      break;
    case "copy":
      if (!action.params.text && !action.params.id) return "Copy action requires 'text' or 'id' param";
      break;
    case "tab_open":
      // url is optional
      break;
    case "tab_switch":
      if (action.params.index === undefined && !action.params.tabId) return "Tab switch requires 'index' or 'tabId' param";
      break;
    case "tab_list":
      break;
    case "tab_close":
      break;
    default:
      return `Unknown action: ${action.action}`;
  }
  return null;
}

/**
 * Attempt to parse natural language response as an action.
 * Fallback when LLM doesn't respond with clean JSON.
 */
function parseFreeform(text) {
  const lower = text.toLowerCase();
  
  // Check for done/complete signals
  if (lower.includes("task complete") || lower.includes("task is complete") || lower.includes("i'm done")) {
    return { action: "done", params: { result: text }, reasoning: text };
  }
  
  // Check for navigate intent
  const urlMatch = text.match(/(?:navigate|go|open|visit)\s+(?:to\s+)?(?:the\s+)?(?:url\s+)?[`"']?(https?:\/\/[^\s`"']+)/i);
  if (urlMatch) {
    return { action: "navigate", params: { url: urlMatch[1] }, reasoning: text };
  }
  
  // Can't parse — return as error with the raw text
  return {
    error: "Could not parse LLM response as action",
    raw: text,
    reasoning: text
  };
}

// Export
if (typeof window !== "undefined") {
  window.__wattbot_parser = { parseResponse };
  window.parseAction = parseResponse;
}
