/**
 * WattBot Wallet Helper v0.2.0
 * High-level wallet functions for sidepanel use.
 * Communicates with wallet-bridge.js via chrome.tabs.sendMessage.
 *
 * Usage:
 *   WattBotWallet.detect().then(result => ...)
 *   WattBotWallet.connect().then(result => ...)
 *   WattBotWallet.getWattBalance(address).then(balance => ...)
 */

var WattBotWallet = (function() {
  "use strict";

  // WATT token mint (Token-2022)
  var WATT_MINT = "5MBiJG6QrhxhxWiJcdWKWq5bQ4wFA6WUrF5YCGSMpump";

  // Solana RPC
  var SOLANA_RPC = "https://api.mainnet-beta.solana.com";

  /**
   * Send a command to the wallet bridge in the active tab
   */
  function sendWalletCommand(command, payload) {
    return new Promise(function(resolve, reject) {
      chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
        if (!tabs || tabs.length === 0) {
          reject(new Error("No active tab found."));
          return;
        }

        chrome.tabs.sendMessage(tabs[0].id, {
          target: "wattbot-wallet",
          command: command,
          payload: payload || {}
        }, function(response) {
          if (chrome.runtime.lastError) {
            reject(new Error(chrome.runtime.lastError.message));
            return;
          }
          if (!response) {
            reject(new Error("No response from wallet bridge."));
            return;
          }
          if (response.error) {
            reject(new Error(response.error));
            return;
          }
          resolve(response);
        });
      });
    });
  }

  /**
   * Detect if Phantom wallet is available on the current page
   * @returns {Promise<{detected, isPhantom, isConnected, publicKey}>}
   */
  function detect() {
    return sendWalletCommand("detect");
  }

  /**
   * Connect to Phantom wallet (triggers user approval popup)
   * @returns {Promise<{connected, publicKey}>}
   */
  function connect() {
    return sendWalletCommand("connect").then(function(result) {
      // Save connected wallet address
      if (result.publicKey) {
        chrome.storage.sync.set({ walletAddress: result.publicKey });
      }
      return result;
    });
  }

  /**
   * Disconnect from Phantom wallet
   * @returns {Promise<{disconnected}>}
   */
  function disconnect() {
    return sendWalletCommand("disconnect").then(function(result) {
      chrome.storage.sync.remove("walletAddress");
      return result;
    });
  }

  /**
   * Sign a message with the connected wallet
   * @param {string} message - Message to sign
   * @returns {Promise<{signature, publicKey}>}
   */
  function signMessage(message) {
    return sendWalletCommand("signMessage", { message: message });
  }

  /**
   * Get WATT token balance for a Solana address.
   * Uses direct Solana RPC — no wallet connection needed, just an address.
   * @param {string} address - Solana public key
   * @returns {Promise<{balance: number, rawBalance: string, decimals: number}>}
   */
  function getWattBalance(address) {
    if (!address) {
      return Promise.reject(new Error("No wallet address provided."));
    }

    // Use getTokenAccountsByOwner to find WATT token accounts
    return fetch(SOLANA_RPC, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "getTokenAccountsByOwner",
        params: [
          address,
          { mint: WATT_MINT },
          { encoding: "jsonParsed" }
        ]
      })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
      if (data.error) {
        throw new Error(data.error.message || "RPC error");
      }

      var accounts = data.result && data.result.value;
      if (!accounts || accounts.length === 0) {
        return { balance: 0, rawBalance: "0", decimals: 6 };
      }

      // Sum balances across all token accounts for this mint
      var totalBalance = 0;
      var decimals = 6;
      accounts.forEach(function(acct) {
        var info = acct.account.data.parsed.info;
        var amount = info.tokenAmount;
        decimals = amount.decimals;
        totalBalance += parseFloat(amount.uiAmountString || "0");
      });

      return {
        balance: totalBalance,
        rawBalance: String(Math.round(totalBalance * Math.pow(10, decimals))),
        decimals: decimals
      };
    });
  }

  /**
   * Get SOL balance for a Solana address
   * @param {string} address - Solana public key
   * @returns {Promise<{balance: number}>}
   */
  function getSolBalance(address) {
    if (!address) {
      return Promise.reject(new Error("No wallet address provided."));
    }

    return fetch(SOLANA_RPC, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        jsonrpc: "2.0",
        id: 1,
        method: "getBalance",
        params: [address]
      })
    })
    .then(function(resp) { return resp.json(); })
    .then(function(data) {
      if (data.error) {
        throw new Error(data.error.message || "RPC error");
      }
      var lamports = data.result && data.result.value || 0;
      return { balance: lamports / 1e9 }; // Convert lamports to SOL
    });
  }

  /**
   * Get the saved wallet address from storage
   * @returns {Promise<string|null>}
   */
  function getSavedAddress() {
    return new Promise(function(resolve) {
      chrome.storage.sync.get(["walletAddress"], function(data) {
        resolve(data && data.walletAddress ? data.walletAddress : null);
      });
    });
  }

  /**
   * Format a balance number for display (e.g., 1234567 → "1,234,567")
   */
  function formatBalance(num) {
    if (num === 0) return "0";
    if (num < 0.01) return "<0.01";
    var parts = num.toFixed(2).split(".");
    parts[0] = parts[0].replace(/\B(?=(\d{3})+(?!\d))/g, ",");
    return parts.join(".");
  }

  // Public API
  return {
    detect: detect,
    connect: connect,
    disconnect: disconnect,
    signMessage: signMessage,
    getWattBalance: getWattBalance,
    getSolBalance: getSolBalance,
    getSavedAddress: getSavedAddress,
    formatBalance: formatBalance,
    WATT_MINT: WATT_MINT
  };

})();
