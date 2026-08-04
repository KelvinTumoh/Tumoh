/** Lightweight chat UI controller for the unified WebSocket chat gateway. */

(function () {
  const CHAT_PANEL = document.getElementById("chat-panel");
  const CHAT_LOG = document.getElementById("chat-log");
  const CHAT_INPUT = document.getElementById("chat-input");
  const CHAT_SEND = document.getElementById("chat-send");
  const CHAT_ROOMS = document.getElementById("chat-rooms");
  const TOKEN = new URLSearchParams(window.location.search).get("token") || "";

  let ws = null;
  let currentRoom = "lobby";
  let tenantId = "";
  let userId = "";
  let recording = false;

  function connect() {
    const path = `${window.location.protocol === "https:" ? "wss" : "ws"}://${window.location.host}/ws/chat?token=${encodeURIComponent(TOKEN)}`;
    ws = new WebSocket(path);

    ws.onopen = () => {
      appendSystem("Connected to chat");
      requestPresence();
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      renderMessage(msg);
      if (msg.type === "presence") {
        renderPresence(msg.metadata?.online_users || []);
      }
    };

    ws.onclose = () => {
      appendSystem("Disconnected from chat");
    };

    ws.onerror = (err) => {
      appendSystem(`Chat error: ${err.message || err}`);
    };
  }

  function sendMessage(type, content, attachments = [], metadata = {}) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const message = {
      message_id: crypto.randomUUID(),
      room_id: currentRoom,
      tenant_id: tenantId,
      sender_id: userId,
      type: type || "text",
      content,
      timestamp: new Date().toISOString(),
      attachments,
      metadata,
    };
    ws.send(JSON.stringify({ room_id: currentRoom, message }));
    renderMessage(message, true);
  }

  function appendSystem(text) {
    const div = document.createElement("div");
    div.className = "chat-message system";
    div.textContent = text;
    CHAT_LOG.appendChild(div);
    CHAT_LOG.scrollTop = CHAT_LOG.scrollHeight;
  }

  function renderMessage(msg, local = false) {
    const div = document.createElement("div");
    div.className = `chat-message ${local || msg.sender_id === userId ? "user" : msg.sender_id === "system" ? "system" : "assistant"}`;

    if (msg.type !== "text" && msg.type !== "system" && msg.type !== "presence") {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = msg.type;
      div.appendChild(badge);
    }

    const text = document.createElement("span");
    text.textContent = msg.content;
    div.appendChild(text);

    if (msg.attachments && msg.attachments.length) {
      msg.attachments.forEach((att) => {
        if (att.type === "image" && att.preview) {
          const img = document.createElement("img");
          img.className = "preview";
          img.src = att.preview;
          div.appendChild(img);
        } else if (att.type === "voice" || att.type === "sound") {
          const audio = document.createElement("audio");
          audio.controls = true;
          audio.src = att.path || "";
          div.appendChild(audio);
        } else if (att.type === "pdf") {
          const note = document.createElement("div");
          note.style.fontSize = "0.75rem";
          note.textContent = `PDF: ${att.name || att.path || "uploaded"}`;
          div.appendChild(note);
        }
      });
    }

    CHAT_LOG.appendChild(div);
    CHAT_LOG.scrollTop = CHAT_LOG.scrollHeight;
  }

  function renderPresence(users) {
    Array.from(CHAT_ROOMS.children).forEach((roomEl) => {
      const dot = roomEl.querySelector(".presence-dot");
      dot.classList.remove("online");
    });
    users.forEach((u) => {
      const el = document.getElementById(`room-user-${u}`);
      if (el) el.classList.add("online");
    });
  }

  function requestPresence() {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    ws.send(JSON.stringify({ type: "presence", room_id: currentRoom }));
  }

  function toggleRecord() {
    recording = !recording;
    const btn = document.getElementById("chat-record");
    btn.textContent = recording ? "Stop" : "Voice";
    btn.classList.toggle("recording", recording);
    if (!recording) {
      // Placeholder: real implementation would send actual audio bytes.
      sendMessage("voice", "[voice message]", [{ type: "voice", payload: "" }]);
    }
  }

  function uploadFile(file, type) {
    const reader = new FileReader();
    reader.onload = (e) => {
      sendMessage(type, `[${type} upload]`, [
        { type, name: file.name, payload: e.target.result },
      ]);
    };
    reader.readAsDataURL(file);
  }

  function init() {
    if (!CHAT_PANEL) return;
    connect();

    CHAT_SEND.addEventListener("click", () => {
      const text = CHAT_INPUT.value.trim();
      if (!text) return;
      sendMessage("text", text);
      CHAT_INPUT.value = "";
    });

    CHAT_INPUT.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        CHAT_SEND.click();
      }
    });

    const recordBtn = document.getElementById("chat-record");
    if (recordBtn) recordBtn.addEventListener("click", toggleRecord);

    const imageInput = document.getElementById("chat-image");
    if (imageInput) {
      imageInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
          uploadFile(e.target.files[0], "image");
        }
      });
    }

    const pdfInput = document.getElementById("chat-pdf");
    if (pdfInput) {
      pdfInput.addEventListener("change", (e) => {
        if (e.target.files && e.target.files[0]) {
          uploadFile(e.target.files[0], "pdf");
        }
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
