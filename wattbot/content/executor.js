/**
 * WattBot Action Executor v0.1.2
 * Handles: click, type, scroll, navigate, wait, extract, hover, keypress, copy
 * Supports: contenteditable, React, Shadow DOM wrappers
 */

(function() {
  "use strict";

  function findElement(id) {
    var el = document.querySelector('[data-wattbot-id="' + id + '"]');
    if (!el) throw new Error("Element " + id + " not found on page");
    return el;
  }

  function focusElement(el) {
    el.scrollIntoView({ behavior: "smooth", block: "center" });
    window.dispatchEvent(new CustomEvent("wattbot-highlight", { detail: { element: el } }));
  }

  function isContentEditable(el) {
    if (el.getAttribute("contenteditable") === "true") return true;
    if (el.isContentEditable) return true;
    if (el.getAttribute("role") === "textbox") return true;
    var parent = el.closest("[contenteditable='true']");
    if (parent) return true;
    return false;
  }

  function findEditableTarget(el) {
    if (el.getAttribute("contenteditable") === "true" || el.isContentEditable) return el;
    var child = el.querySelector("[contenteditable='true']");
    if (child) return child;
    var input = el.querySelector("textarea, input[type='text'], input:not([type])");
    if (input) return input;
    var textbox = el.querySelector("[role='textbox']");
    if (textbox) return textbox;
    return el;
  }

  /**
   * Type into contenteditable — uses execCommand for both clearing and inserting
   * so rich text editor frameworks (ProseMirror, Slate, Draft.js) stay in sync.
   */
  function typeIntoContentEditable(el, text, clear) {
    el.focus();

    // Clear using selection + execCommand so editor frameworks process it
    if (clear !== false) {
      // Strategy A: Select all via execCommand, then delete via execCommand
      // This keeps the editor framework in the loop for both operations
      el.focus();
      document.execCommand("selectAll", false, null);
      document.execCommand("delete", false, null);

      // Verify clear worked
      var afterClear = (el.textContent || el.innerText || "").trim();
      if (afterClear.length > 0) {
        // Strategy B: Manual selection range + delete
        var sel = window.getSelection();
        var range = document.createRange();
        range.selectNodeContents(el);
        sel.removeAllRanges();
        sel.addRange(range);
        document.execCommand("delete", false, null);
      }

      afterClear = (el.textContent || el.innerText || "").trim();
      if (afterClear.length > 0) {
        // Strategy C: Last resort — nuke DOM directly
        el.innerHTML = "";
        el.textContent = "";
        el.dispatchEvent(new Event("input", { bubbles: true }));
      }

      // Re-focus after clearing
      el.focus();
    }

    // Insert text via execCommand (editor frameworks listen to this)
    var inserted = document.execCommand("insertText", false, text);

    // Verify text actually landed
    var currentText = el.textContent || el.innerText || "";
    if (!inserted || currentText.trim() === "") {
      // Fallback: InputEvent (some editors respond to this)
      el.focus();
      el.dispatchEvent(new InputEvent("beforeinput", {
        inputType: "insertText", data: text, bubbles: true, cancelable: true
      }));
      el.dispatchEvent(new InputEvent("input", {
        inputType: "insertText", data: text, bubbles: true
      }));
      currentText = el.textContent || el.innerText || "";
    }

    if (currentText.trim() === "") {
      // Last resort: direct text set + events
      el.textContent = text;
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      currentText = el.textContent || el.innerText || "";
    }

    return { success: currentText.indexOf(text) !== -1, actualText: currentText.trim() };
  }

  function typeIntoInput(el, text, clear) {
    el.focus();

    var nativeInputSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
    var nativeTextareaSetter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value");
    var setter = el.tagName === "TEXTAREA" ? nativeTextareaSetter : nativeInputSetter;

    if (clear !== false) {
      if (setter && setter.set) { setter.set.call(el, ""); } else { el.value = ""; }
      el.dispatchEvent(new Event("input", { bubbles: true }));
    }

    if (setter && setter.set) { setter.set.call(el, text); } else { el.value = text; }

    var tracker = el._valueTracker;
    if (tracker) tracker.setValue("");

    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));

    return { success: true, actualText: el.value };
  }

  // --- Actions ---

  function executeClick(params) {
    var el = findElement(params.id);
    focusElement(el);
    return new Promise(function(resolve) {
      setTimeout(function() {
        el.click();
        resolve({ success: true, action: "click", id: params.id });
      }, 300);
    });
  }

  function executeType(params) {
    var el = findElement(params.id);
    focusElement(el);
    return new Promise(function(resolve) {
      setTimeout(function() {
        var target = findEditableTarget(el);
        var method;

        if (isContentEditable(target)) {
          // Contenteditable path: clear via execCommand so editor frameworks sync,
          // then delay, then insert, then Enter
          method = "contenteditable";

          // Step 1: Clear using execCommand (ProseMirror/Slate listen to this)
          if (params.clear !== false) {
            target.focus();
            document.execCommand("selectAll", false, null);
            document.execCommand("delete", false, null);

            // Verify clear worked, retry with manual selection if needed
            var afterClear = (target.textContent || target.innerText || "").trim();
            if (afterClear.length > 0) {
              var sel = window.getSelection();
              var range = document.createRange();
              range.selectNodeContents(target);
              sel.removeAllRanges();
              sel.addRange(range);
              document.execCommand("delete", false, null);
            }

            // Last resort: nuke DOM
            afterClear = (target.textContent || target.innerText || "").trim();
            if (afterClear.length > 0) {
              target.innerHTML = "";
              target.dispatchEvent(new Event("input", { bubbles: true }));
            }
          }

          // Step 2: Delay to let editor framework process the clear
          setTimeout(function() {
            target.focus();

            // Step 3: Insert text via execCommand
            var inserted = document.execCommand("insertText", false, params.text);
            var currentText = (target.textContent || target.innerText || "").trim();

            if (!inserted || currentText === "") {
              // Fallback: InputEvent
              target.dispatchEvent(new InputEvent("beforeinput", {
                inputType: "insertText", data: params.text, bubbles: true, cancelable: true
              }));
              target.dispatchEvent(new InputEvent("input", {
                inputType: "insertText", data: params.text, bubbles: true
              }));
              currentText = (target.textContent || target.innerText || "").trim();
            }

            if (currentText === "") {
              // Last resort: direct set
              target.textContent = params.text;
              target.dispatchEvent(new Event("input", { bubbles: true }));
              currentText = params.text;
            }

            // Step 4: Press Enter after another small delay
            if (params.pressEnter) {
              setTimeout(function() {
                var kbdOpts = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true };
                target.dispatchEvent(new KeyboardEvent("keydown", kbdOpts));
                target.dispatchEvent(new KeyboardEvent("keypress", kbdOpts));
                target.dispatchEvent(new KeyboardEvent("keyup", kbdOpts));
              }, 150);
            }

            resolve({
              success: currentText.indexOf(params.text) !== -1,
              action: "type",
              id: params.id,
              text: params.text,
              actualText: currentText,
              method: method,
              contentEditable: true
            });
          }, 200); // 200ms delay between clear and insert

          return; // Early return — resolve called inside setTimeout
        }

        // Standard input/textarea path (unchanged)
        var result;
        if (target.tagName === "INPUT" || target.tagName === "TEXTAREA") {
          result = typeIntoInput(target, params.text, params.clear);
          method = "input-native-setter";
        } else {
          result = typeIntoContentEditable(target, params.text, params.clear);
          method = "fallback";
        }

        if (params.pressEnter) {
          setTimeout(function() {
            var kbdOpts = { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true };
            target.dispatchEvent(new KeyboardEvent("keydown", kbdOpts));
            target.dispatchEvent(new KeyboardEvent("keypress", kbdOpts));
            target.dispatchEvent(new KeyboardEvent("keyup", kbdOpts));
            var form = target.closest("form");
            if (form) form.dispatchEvent(new Event("submit", { bubbles: true }));
          }, 100);
        }

        resolve({
          success: result.success,
          action: "type",
          id: params.id,
          text: params.text,
          actualText: result.actualText,
          method: method,
          contentEditable: false
        });
      }, 400);
    });
  }

  function executeSelect(params) {
    var el = findElement(params.id);
    focusElement(el);
    return new Promise(function(resolve) {
      setTimeout(function() {
        el.value = params.value;
        el.dispatchEvent(new Event("change", { bubbles: true }));
        el.dispatchEvent(new Event("input", { bubbles: true }));
        resolve({ success: true, action: "select", id: params.id, value: params.value });
      }, 300);
    });
  }

  function executeScroll(params) {
    var direction = params.direction || "down";
    var amount = params.amount || 500;
    if (direction === "down") window.scrollBy({ top: amount, behavior: "smooth" });
    else if (direction === "up") window.scrollBy({ top: -amount, behavior: "smooth" });
    else if (direction === "top") window.scrollTo({ top: 0, behavior: "smooth" });
    else if (direction === "bottom") window.scrollTo({ top: document.documentElement.scrollHeight, behavior: "smooth" });
    return Promise.resolve({ success: true, action: "scroll", direction: direction });
  }

  function executeWait(params) {
    var ms = params.ms || 1000;
    return new Promise(function(resolve) {
      setTimeout(function() { resolve({ success: true, action: "wait", ms: ms }); }, ms);
    });
  }

  function executeExtract(params) {
    if (params.selector) {
      var elements = document.querySelectorAll(params.selector);
      var texts = Array.from(elements).map(function(el) { return el.innerText.trim(); }).filter(function(t) { return t; });
      return Promise.resolve({ success: true, action: "extract", data: texts.join("\n") });
    }
    var text = document.body.innerText.substring(0, 5000);
    return Promise.resolve({ success: true, action: "extract", data: text });
  }

  /**
   * Hover action — triggers mouseover/mouseenter events.
   */
  function executeHover(params) {
    var el = findElement(params.id);
    focusElement(el);
    return new Promise(function(resolve) {
      setTimeout(function() {
        var rect = el.getBoundingClientRect();
        var cx = rect.left + rect.width / 2;
        var cy = rect.top + rect.height / 2;
        var eventOpts = { bubbles: true, clientX: cx, clientY: cy };
        el.dispatchEvent(new MouseEvent("mouseenter", eventOpts));
        el.dispatchEvent(new MouseEvent("mouseover", eventOpts));
        el.dispatchEvent(new MouseEvent("mousemove", eventOpts));
        // Hold hover for a moment to let tooltips/menus render
        setTimeout(function() {
          resolve({ success: true, action: "hover", id: params.id });
        }, params.duration || 500);
      }, 300);
    });
  }

  /**
   * Keypress action — send keyboard events (Escape, Tab, arrows, etc.)
   */
  function executeKeypress(params) {
    var key = params.key || "Escape";
    var target = params.id ? findElement(params.id) : document.activeElement || document.body;
    var kbdOpts = {
      key: key,
      code: params.code || key,
      keyCode: params.keyCode || 0,
      which: params.keyCode || 0,
      bubbles: true,
      shiftKey: !!params.shift,
      ctrlKey: !!params.ctrl,
      altKey: !!params.alt,
      metaKey: !!params.meta
    };
    target.dispatchEvent(new KeyboardEvent("keydown", kbdOpts));
    target.dispatchEvent(new KeyboardEvent("keypress", kbdOpts));
    target.dispatchEvent(new KeyboardEvent("keyup", kbdOpts));
    return Promise.resolve({ success: true, action: "keypress", key: key });
  }

  /**
   * Copy action — copy text to clipboard.
   */
  function executeCopy(params) {
    var text = params.text || "";
    // If no text provided but element id given, extract from element
    if (!text && params.id) {
      var el = findElement(params.id);
      text = el.innerText || el.textContent || el.value || "";
    }
    return navigator.clipboard.writeText(text).then(function() {
      return { success: true, action: "copy", length: text.length };
    }).catch(function(e) {
      return { success: false, action: "copy", error: e.message };
    });
  }

  // --- Dispatcher ---

  function executeAction(action) {
    try {
      switch (action.action) {
        case "click": return executeClick(action.params);
        case "type": return executeType(action.params);
        case "select": return executeSelect(action.params);
        case "scroll": return executeScroll(action.params);
        case "wait": return executeWait(action.params);
        case "extract": return executeExtract(action.params);
        case "hover": return executeHover(action.params);
        case "keypress": return executeKeypress(action.params);
        case "copy": return executeCopy(action.params);
        default: return Promise.resolve({ error: "Unknown action: " + action.action });
      }
    } catch (e) {
      return Promise.resolve({ error: e.message, action: action.action });
    }
  }

  chrome.runtime.onMessage.addListener(function(message, sender, sendResponse) {
    if (message.type === "EXECUTE_ACTION") {
      executeAction(message.action).then(function(result) {
        sendResponse(result);
      });
      return true;
    }
  });

  console.log("[WattBot] Action executor v0.1.2 loaded");
})();
