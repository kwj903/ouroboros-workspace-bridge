// ==UserScript==
// @name         Ouroboros Workspace Bridge Companion
// @namespace    https://github.com/kwj903/ouroboros-workspace-bridge
// @version      0.1.0
// @description  Import ouroboros-intent blocks from ChatGPT into the local pending UI and copy handoffs back safely.
// @match        https://chatgpt.com/*
// @match        https://chat.openai.com/*
// @grant        GM_setClipboard
// @connect      127.0.0.1
// ==/UserScript==

(function () {
  "use strict";

  const config = {
    reviewOrigin: "http://127.0.0.1:8790",
    pollMs: 1500,
    maxPolls: 120,
    autoSubmit: false,
  };

  const seen = new Set();

  function stableStringify(value) {
    if (Array.isArray(value)) {
      return "[" + value.map(stableStringify).join(",") + "]";
    }
    if (value && typeof value === "object") {
      return "{" + Object.keys(value).sort().map((key) => JSON.stringify(key) + ":" + stableStringify(value[key])).join(",") + "}";
    }
    return JSON.stringify(value);
  }

  function notice(message) {
    let node = document.getElementById("ouroboros-companion-notice");
    if (!node) {
      node = document.createElement("div");
      node.id = "ouroboros-companion-notice";
      node.style.cssText = [
        "position:fixed",
        "right:18px",
        "bottom:18px",
        "z-index:2147483647",
        "max-width:360px",
        "padding:12px 14px",
        "border-radius:10px",
        "background:#111827",
        "color:white",
        "font:13px -apple-system,BlinkMacSystemFont,Segoe UI,sans-serif",
        "box-shadow:0 8px 24px rgba(0,0,0,.22)",
        "white-space:pre-wrap",
      ].join(";");
      document.body.appendChild(node);
    }
    node.textContent = message;
    window.setTimeout(() => {
      if (node && node.parentNode) {
        node.parentNode.removeChild(node);
      }
    }, 7000);
  }

  async function postIntent(intent) {
    const response = await fetch(config.reviewOrigin + "/intents/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(intent),
    });
    const payload = await response.json();
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || "Intent import failed.");
    }
    return payload;
  }

  async function latestHandoff() {
    const response = await fetch(config.reviewOrigin + "/handoffs/latest", { cache: "no-store" });
    if (!response.ok) {
      return null;
    }
    const payload = await response.json();
    return payload && payload.handoff ? payload.handoff : null;
  }

  async function waitForHandoff(bundleId) {
    for (let i = 0; i < config.maxPolls; i += 1) {
      const handoff = await latestHandoff();
      if (handoff && handoff.bundle_id === bundleId) {
        return handoff;
      }
      await new Promise((resolve) => window.setTimeout(resolve, config.pollMs));
    }
    return null;
  }

  function handoffMessage(handoff) {
    return [
      "Ouroboros handoff:",
      "",
      "```json",
      JSON.stringify({
        bundle_id: handoff.bundle_id,
        status: handoff.status,
        ok: handoff.ok,
        next: handoff.next,
        stdout_tail: handoff.stdout_tail || "",
        stderr_tail: handoff.stderr_tail || "",
      }, null, 2),
      "```",
    ].join("\n");
  }

  async function copyText(text) {
    if (typeof GM_setClipboard === "function") {
      GM_setClipboard(text, "text");
      return;
    }
    await navigator.clipboard.writeText(text);
  }

  function findComposer() {
    return document.querySelector("textarea") || document.querySelector('[contenteditable="true"]');
  }

  async function prepareChatGPTMessage(handoff) {
    const message = handoffMessage(handoff);
    const composer = findComposer();
    if (composer) {
      composer.focus();
      if ("value" in composer) {
        composer.value = message;
        composer.dispatchEvent(new Event("input", { bubbles: true }));
      } else {
        composer.textContent = message;
        composer.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: message }));
      }
      notice("Ouroboros handoff prepared in the composer. Review before sending.");
      return;
    }
    await copyText(message);
    notice("Ouroboros handoff copied to clipboard. Paste it into ChatGPT to continue.");
  }

  function parseIntentBlocks() {
    const blocks = Array.from(document.querySelectorAll("pre code, code"));
    const intents = [];
    for (const block of blocks) {
      const lang = Array.from(block.classList).join(" ");
      const parentLang = block.parentElement ? Array.from(block.parentElement.classList).join(" ") : "";
      const marker = (lang + " " + parentLang).toLowerCase();
      if (!marker.includes("ouroboros-intent")) {
        continue;
      }
      try {
        const intent = JSON.parse(block.textContent || "");
        if (
          intent &&
          intent.version === 1 &&
          intent.intent_kind === "run" &&
          typeof intent.intent_type === "string"
        ) {
          intents.push(intent);
        }
      } catch (_error) {
        // Ignore partial or invalid blocks while ChatGPT is still streaming.
      }
    }
    return intents;
  }

  async function handleIntent(intent) {
    const key = stableStringify(intent);
    if (seen.has(key)) {
      return;
    }
    seen.add(key);

    try {
      notice("Importing Ouroboros intent into local pending UI...");
      const result = await postIntent(intent);
      const pendingUrl = config.reviewOrigin + String(result.pending_url || ("/pending?bundle_id=" + result.bundle_id));
      window.open(pendingUrl, "ouroboros-review");
      notice("Intent imported. Approve locally in the pending UI.");

      const handoff = await waitForHandoff(String(result.bundle_id));
      if (handoff) {
        await prepareChatGPTMessage(handoff);
      } else {
        notice("Intent imported. Waiting timed out; use the pending UI or workspace_next_handoff.");
      }
    } catch (error) {
      notice("Ouroboros companion error: " + (error && error.message ? error.message : String(error)));
    }
  }

  function scan() {
    for (const intent of parseIntentBlocks()) {
      handleIntent(intent);
    }
  }

  const observer = new MutationObserver(scan);
  observer.observe(document.documentElement, { childList: true, subtree: true });
  window.setInterval(scan, 3000);
  scan();
}());
