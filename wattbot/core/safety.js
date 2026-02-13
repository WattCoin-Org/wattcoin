/**
 * WattBot Safety
 * Classifies actions into safe (auto-execute), confirm (ask user), block (prevent).
 */

const DANGEROUS_KEYWORDS = [
  "buy", "purchase", "order", "checkout", "pay", "submit payment",
  "delete", "remove", "cancel subscription", "close account",
  "transfer", "send money", "wire", "withdraw"
];

const DANGEROUS_INPUT_TYPES = ["password", "credit-card", "cc-number"];

/**
 * Classify an action's safety level.
 * @returns {string} "safe" | "confirm" | "block"
 */
function classifyAction(action, pageState) {
  if (!action) return "block";
  
  const actionType = action.action;
  
  // Read-only actions are always safe
  if (["scroll", "wait", "extract", "done", "hover", "keypress", "tab_list", "copy"].includes(actionType)) {
    return "safe";
  }
  
  // Navigate and tab management are generally safe
  if (actionType === "navigate" || actionType === "tab_open" || actionType === "tab_switch") {
    return "safe";
  }

  // Tab close needs confirmation
  if (actionType === "tab_close") {
    return "confirm";
  }
  
  // Click actions need inspection
  if (actionType === "click") {
    const id = action.params?.id;
    if (!id) return "confirm";
    
    // Look up element label from page state
    const elementLine = findElementInState(id, pageState);
    if (!elementLine) return "confirm";
    
    const lower = elementLine.toLowerCase();
    
    // Submit buttons always need confirmation
    if (lower.includes("submit-button")) return "confirm";
    
    // Check for dangerous keywords
    for (const kw of DANGEROUS_KEYWORDS) {
      if (lower.includes(kw)) return "confirm";
    }
    
    return "safe";
  }
  
  // Type actions — check what field we're typing into
  if (actionType === "type") {
    const id = action.params?.id;
    if (!id) return "confirm";
    
    const elementLine = findElementInState(id, pageState);
    if (!elementLine) return "confirm";
    
    const lower = elementLine.toLowerCase();
    
    // Password fields always need confirmation
    if (lower.includes("password")) return "confirm";
    
    // Payment-related fields
    if (lower.includes("card") || lower.includes("cvv") || lower.includes("expir")) return "confirm";
    
    return "safe";
  }
  
  // Select actions are generally safe
  if (actionType === "select") return "safe";
  
  // Unknown actions need confirmation
  return "confirm";
}

/**
 * Find element description in page state interactive elements text.
 */
function findElementInState(id, pageState) {
  if (!pageState) return null;
  // Handle raw capture format (elements array)
  if (pageState.elements && Array.isArray(pageState.elements)) {
    var el = pageState.elements.find(function(e) { return e.id === id; });
    if (el) return "[" + el.id + "] " + el.type + ' "' + (el.label || "") + '"';
    return null;
  }
  // Handle string format
  if (pageState.interactiveElements) {
    var lines = pageState.interactiveElements.split("\n");
    return lines.find(function(line) { return line.startsWith("[" + id + "]"); }) || null;
  }
  return null;
}

/**
 * Get human-readable description of why confirmation is needed.
 */
function getConfirmReason(action, pageState) {
  const elementLine = findElementInState(action.params?.id, pageState);
  const label = elementLine || action.params?.id || "unknown element";
  
  switch (action.action) {
    case "click":
      return `Click "${label}" — this may submit data or make a purchase.`;
    case "type":
      return `Type into "${label}" — this may be a sensitive field.`;
    default:
      return `${action.action} on "${label}" — confirm to proceed.`;
  }
}

// Export for use in agent.js
if (typeof window !== "undefined") {
  window.__wattbot_safety = { classifyAction, getConfirmReason };
  window.checkSafety = function(action, pageState) {
    var level = classifyAction(action, pageState);
    var reason = level !== "safe" ? getConfirmReason(action, pageState) : "";
    return { level: level, reason: reason };
  };
}
