// In production FastAPI serves the frontend, so relative URLs work everywhere.
// In local dev, open via http://localhost:8000 (not file://) and it works too.
const API = "";

// ---------------------------------------------------------------------------
// Session bootstrap
// ---------------------------------------------------------------------------

let sessionId = localStorage.getItem("golf_session_id");

async function initSession() {
  if (sessionId) return;
  const res = await fetch(`${API}/session/new`, { method: "POST" });
  const data = await res.json();
  sessionId = data.session_id;
  localStorage.setItem("golf_session_id", sessionId);
}

initSession();

// ---------------------------------------------------------------------------
// Chat
// ---------------------------------------------------------------------------

const chatMessages = document.getElementById("chat-messages");
const chatForm = document.getElementById("chat-form");
const chatInput = document.getElementById("chat-input");
const sendBtn = document.getElementById("send-btn");

function appendMessage(role, text) {
  const div = document.createElement("div");
  div.className = `message message-${role}`;
  const content = document.createElement("div");
  content.className = "message-content";
  content.textContent = text;
  div.appendChild(content);
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return content;
}

function showTyping() {
  const div = document.createElement("div");
  div.className = "message message-assistant";
  div.id = "typing-indicator";
  div.innerHTML = `<div class="message-content typing-dots"><span></span><span></span><span></span></div>`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTyping() {
  const el = document.getElementById("typing-indicator");
  if (el) el.remove();
}

chatForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const message = chatInput.value.trim();
  if (!message) return;

  chatInput.value = "";
  sendBtn.disabled = true;

  appendMessage("user", message);
  showTyping();

  try {
    const res = await fetch(`${API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, message }),
    });

    const data = await res.json();
    removeTyping();

    if (res.ok) {
      appendMessage("assistant", data.response);
    } else {
      appendMessage("assistant", `Error: ${data.detail || "Something went wrong."}`);
    }
  } catch (err) {
    removeTyping();
    appendMessage("assistant", `Network error: ${err.message}`);
  } finally {
    sendBtn.disabled = false;
    chatInput.focus();
  }
});

// ---------------------------------------------------------------------------
// CSV Upload
// ---------------------------------------------------------------------------

const csvInput = document.getElementById("csv-input");
const courseStatus = document.getElementById("course-status");

document.querySelector(".upload-label").addEventListener("click", () => csvInput.click());

csvInput.addEventListener("change", async () => {
  const file = csvInput.files[0];
  if (!file) return;

  courseStatus.textContent = "Uploading...";
  courseStatus.className = "status-badge status-empty";

  const formData = new FormData();
  formData.append("file", file);
  formData.append("session_id", sessionId);

  try {
    const res = await fetch(`${API}/upload-course`, {
      method: "POST",
      body: formData,
    });
    const data = await res.json();

    if (res.ok) {
      courseStatus.textContent = `${data.course_name} (${data.hole_count} holes)`;
      courseStatus.className = data.warnings.length > 0
        ? "status-badge status-warn"
        : "status-badge status-ok";
      appendMessage("assistant", data.message);
    } else {
      courseStatus.textContent = "Upload failed";
      courseStatus.className = "status-badge status-warn";
      appendMessage("assistant", `Course upload error: ${data.detail}`);
    }
  } catch (err) {
    courseStatus.textContent = "Upload error";
    courseStatus.className = "status-badge status-warn";
    appendMessage("assistant", `Upload failed: ${err.message}`);
  }

  csvInput.value = "";
});

// ---------------------------------------------------------------------------
// Player Profile
// ---------------------------------------------------------------------------

const profileForm = document.getElementById("profile-form");
const profileStatus = document.getElementById("profile-status");

profileForm.addEventListener("submit", async (e) => {
  e.preventDefault();

  const handicap = parseFloat(document.getElementById("handicap").value) || null;

  const clubDistances = {};
  document.querySelectorAll(".club-dist").forEach((input) => {
    if (input.value) {
      clubDistances[input.dataset.club] = parseInt(input.value, 10);
    }
  });

  const profile = {
    handicap,
    club_distances: Object.keys(clubDistances).length > 0 ? clubDistances : null,
  };

  try {
    const res = await fetch(`${API}/player-profile`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: sessionId, profile }),
    });
    const data = await res.json();

    if (res.ok) {
      profileStatus.textContent = `HCP ${handicap ?? "not set"}`;
      profileStatus.className = "status-badge status-ok";
      appendMessage("assistant", `Got it! Profile saved — HCP ${handicap ?? "not set"}. I'll factor this into all my recommendations.`);
    } else {
      profileStatus.textContent = "Save failed";
      profileStatus.className = "status-badge status-warn";
    }
  } catch (err) {
    appendMessage("assistant", `Profile save error: ${err.message}`);
  }
});
