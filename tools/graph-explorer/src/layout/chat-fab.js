/**
 * Persistent Chat FAB — floating action button & slide-out chat drawer.
 *
 * Renders a floating button in the bottom-right corner of the application.
 * Clicking it toggles a slide-out chat panel that is persistent across navigation.
 */

let isChatOpen = false;
let chatHistory = [];

/**
 * Initialize the Chat FAB. Call once on application load.
 */
export function initChatFab() {
  // Prevent duplicate initialization
  if (document.getElementById("pragma-chat-container")) return;

  const container = document.createElement("div");
  container.id = "pragma-chat-container";
  container.innerHTML = `
    <!-- Floating Action Button -->
    <button class="chat-fab" id="chat-fab" title="Open Chat">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
      </svg>
    </button>

    <!-- Slide-out Drawer -->
    <div class="chat-drawer" id="chat-drawer">
      <div class="chat-drawer-header">
        <div class="chat-drawer-title">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
          </svg>
          <span>Pragma Assistant</span>
        </div>
        <button class="chat-drawer-close" id="chat-drawer-close" title="Close Chat">&times;</button>
      </div>

      <div class="chat-drawer-messages" id="chat-messages">
        <div class="chat-turn system">
          <div class="chat-role">System</div>
          <div class="chat-text">Welcome to Pragma! How can I help you explore or customize your site architecture today?</div>
        </div>
      </div>

      <div class="chat-drawer-footer">
        <form id="chat-form" class="chat-form">
          <input type="text" id="chat-input" placeholder="Type a message..." required autocomplete="off" />
          <button type="submit" id="chat-submit">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <line x1="22" y1="2" x2="11" y2="13"></line>
              <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
            </svg>
          </button>
        </form>
      </div>
    </div>
  `;

  document.body.appendChild(container);

  // Wire up event listeners
  const fab = document.getElementById("chat-fab");
  const drawer = document.getElementById("chat-drawer");
  const closeBtn = document.getElementById("chat-drawer-close");
  const form = document.getElementById("chat-form");
  const input = document.getElementById("chat-input");

  fab.addEventListener("click", toggleChat);
  closeBtn.addEventListener("click", toggleChat);
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const msg = input.value.trim();
    if (msg) {
      handleUserMessage(msg);
      input.value = "";
    }
  });

  // Load existing chat history if any
  renderHistory();
}

function toggleChat() {
  isChatOpen = !isChatOpen;
  const drawer = document.getElementById("chat-drawer");
  const fab = document.getElementById("chat-fab");

  if (isChatOpen) {
    drawer.classList.add("open");
    fab.classList.add("active");
    document.getElementById("chat-input").focus();
    // Scroll messages to bottom
    const msgs = document.getElementById("chat-messages");
    msgs.scrollTop = msgs.scrollHeight;
  } else {
    drawer.classList.remove("open");
    fab.classList.remove("active");
  }
}

function handleUserMessage(text) {
  // Add to history
  chatHistory.push({ role: "user", content: text });
  renderHistory();

  // Show loading indicator
  showAssistantLoading();

  // Try to send to the backend, or fallback to mock
  // Context-scoping logic: check if we are on a specific document
  const currentDoc = getActiveDocumentContext();

  fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: text,
      history: chatHistory.slice(0, -1), // previous history
      context: currentDoc ? { filename: currentDoc } : null
    })
  })
    .then((res) => {
      if (!res.ok) throw new Error("API not ready or returned error");
      return res.json();
    })
    .then((data) => {
      removeAssistantLoading();
      chatHistory.push({ role: "assistant", content: data.reply });
      renderHistory();
    })
    .catch((err) => {
      // Mock / fallback response for prototype demo
      setTimeout(() => {
        removeAssistantLoading();
        let reply = "";
        if (currentDoc) {
          reply = `🤖 **[Prototype Mode]** for document \`${currentDoc}\`:\n\nOnce the backend is implemented, I will ground my response in the schema and contents of this document. Currently, I see you are editing/viewing \`${currentDoc}\`.`;
        } else {
          reply = `🤖 **[Prototype Mode]** (Global Context):\n\nI am the persistent FAB chat. When the backend REST endpoints are completed, I will query the live Kùzu graph database to answer queries about components, endpoints, and requirements across the entire session.`;
        }
        chatHistory.push({ role: "assistant", content: reply });
        renderHistory();
      }, 800);
    });
}

function renderHistory() {
  const msgsEl = document.getElementById("chat-messages");
  if (!msgsEl) return;

  // Keep system welcome
  let html = `
    <div class="chat-turn system">
      <div class="chat-role">System</div>
      <div class="chat-text">Welcome to Pragma! How can I help you explore or customize your site architecture today?</div>
    </div>
  `;

  chatHistory.forEach((turn) => {
    const isUser = turn.role === "user";
    html += `
      <div class="chat-turn ${isUser ? "user" : "assistant"}">
        <div class="chat-role">${isUser ? "You" : "Assistant"}</div>
        <div class="chat-text">${escapeHtml(turn.content)}</div>
      </div>
    `;
  });

  msgsEl.innerHTML = html;
  msgsEl.scrollTop = msgsEl.scrollHeight;
}

function showAssistantLoading() {
  const msgsEl = document.getElementById("chat-messages");
  const loading = document.createElement("div");
  loading.id = "chat-loading-indicator";
  loading.className = "chat-turn assistant loading";
  loading.innerHTML = `
    <div class="chat-role">Assistant</div>
    <div class="chat-text">
      <span class="dot"></span>
      <span class="dot"></span>
      <span class="dot"></span>
    </div>
  `;
  msgsEl.appendChild(loading);
  msgsEl.scrollTop = msgsEl.scrollHeight;
}

function removeAssistantLoading() {
  const loading = document.getElementById("chat-loading-indicator");
  if (loading) loading.remove();
}

function getActiveDocumentContext() {
  // Simple check based on URL hash or active page
  const hash = window.location.hash || "";
  if (hash.startsWith("#/documents/")) {
    return hash.replace("#/documents/", "");
  }
  // Fallback check if index.html?doc=xyz is used in query string
  const urlParams = new URLSearchParams(window.location.search);
  return urlParams.get("doc");
}

function escapeHtml(text) {
  if (typeof text !== "string") return text;
  // Preserve simple markdown bold/monospace formatting for clean prototype styling
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;")
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br/>");
}
