/**
 * WattBot Wallet Inject — Page Context Script
 * This runs in the PAGE context (not extension context) so it can access window.phantom.
 * Communication: window.postMessage ↔ content script (wallet-bridge.js)
 * 
 * IMPORTANT: This file has NO access to chrome.* APIs.
 */

(function() {
  "use strict";

  var WATTBOT_MSG = "WATTBOT_WALLET";
  var WATTBOT_RESP = "WATTBOT_WALLET_RESPONSE";

  // Listen for commands from the content script
  window.addEventListener("message", function(event) {
    // Only accept messages from same window
    if (event.source !== window) return;
    if (!event.data || event.data.type !== WATTBOT_MSG) return;

    var command = event.data.command;
    var requestId = event.data.requestId;

    switch (command) {
      case "detect":
        handleDetect(requestId);
        break;
      case "connect":
        handleConnect(requestId);
        break;
      case "disconnect":
        handleDisconnect(requestId);
        break;
      case "signMessage":
        handleSignMessage(requestId, event.data.payload);
        break;
      case "signTransaction":
        handleSignTransaction(requestId, event.data.payload);
        break;
      default:
        respond(requestId, { error: "Unknown command: " + command });
    }
  });

  function respond(requestId, data) {
    window.postMessage({
      type: WATTBOT_RESP,
      requestId: requestId,
      data: data
    }, "*");
  }

  function getProvider() {
    if (window.phantom && window.phantom.solana && window.phantom.solana.isPhantom) {
      return window.phantom.solana;
    }
    // Also check legacy location
    if (window.solana && window.solana.isPhantom) {
      return window.solana;
    }
    return null;
  }

  function handleDetect(requestId) {
    var provider = getProvider();
    respond(requestId, {
      detected: !!provider,
      isPhantom: provider ? !!provider.isPhantom : false,
      isConnected: provider ? provider.isConnected : false,
      publicKey: (provider && provider.isConnected && provider.publicKey)
        ? provider.publicKey.toString()
        : null
    });
  }

  function handleConnect(requestId) {
    var provider = getProvider();
    if (!provider) {
      respond(requestId, { error: "Phantom wallet not detected. Please install Phantom." });
      return;
    }

    provider.connect()
      .then(function(resp) {
        var publicKey = resp.publicKey.toString();
        respond(requestId, {
          connected: true,
          publicKey: publicKey
        });
      })
      .catch(function(err) {
        respond(requestId, {
          error: err.message || "User rejected the connection request."
        });
      });
  }

  function handleDisconnect(requestId) {
    var provider = getProvider();
    if (!provider) {
      respond(requestId, { disconnected: true });
      return;
    }

    provider.disconnect()
      .then(function() {
        respond(requestId, { disconnected: true });
      })
      .catch(function(err) {
        respond(requestId, { error: err.message || "Failed to disconnect." });
      });
  }

  function handleSignMessage(requestId, payload) {
    var provider = getProvider();
    if (!provider) {
      respond(requestId, { error: "Phantom wallet not detected." });
      return;
    }

    if (!provider.isConnected) {
      respond(requestId, { error: "Wallet not connected. Connect first." });
      return;
    }

    var message = new TextEncoder().encode(payload.message);
    provider.signMessage(message, "utf8")
      .then(function(result) {
        // Convert signature Uint8Array to hex string for transport
        var sigHex = Array.from(result.signature).map(function(b) {
          return ("0" + b.toString(16)).slice(-2);
        }).join("");
        respond(requestId, {
          signature: sigHex,
          publicKey: result.publicKey.toString()
        });
      })
      .catch(function(err) {
        respond(requestId, { error: err.message || "User rejected signing." });
      });
  }

  function handleSignTransaction(requestId, payload) {
    var provider = getProvider();
    if (!provider) {
      respond(requestId, { error: "Phantom wallet not detected." });
      return;
    }

    if (!provider.isConnected) {
      respond(requestId, { error: "Wallet not connected. Connect first." });
      return;
    }

    // payload.transaction is a base64-encoded serialized transaction
    // We need to deserialize it — but we don't have @solana/web3.js here.
    // Instead, we receive the raw bytes and construct a VersionedTransaction or Transaction.
    // For now, we'll use signAndSendTransaction with raw bytes.
    try {
      var txBytes = Uint8Array.from(atob(payload.transaction), function(c) { return c.charCodeAt(0); });

      // Try VersionedTransaction first (modern), fallback to legacy
      // Phantom's signAndSendTransaction accepts both
      provider.request({
        method: "signAndSendTransaction",
        params: {
          message: btoa(String.fromCharCode.apply(null, txBytes)),
          options: {
            skipPreflight: false,
            preflightCommitment: "confirmed"
          }
        }
      })
      .then(function(result) {
        respond(requestId, {
          signature: result.signature,
          publicKey: result.publicKey ? result.publicKey.toString() : null
        });
      })
      .catch(function(err) {
        respond(requestId, { error: err.message || "Transaction signing failed." });
      });
    } catch (e) {
      respond(requestId, { error: "Invalid transaction data: " + e.message });
    }
  }

  // Signal that the inject script is ready
  window.postMessage({
    type: WATTBOT_RESP,
    requestId: "__init__",
    data: { ready: true }
  }, "*");
})();
