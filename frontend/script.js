const state = {
    token: localStorage.getItem("lifeos_token"),
    user: null,
};

const $ = (id) => document.getElementById(id);
const pages = document.querySelectorAll(".page");
const menuItems = document.querySelectorAll(".menu-item");
const titles = { dashboard: "Dashboard", chat: "Agent", tasks: "Tasks", knowledge: "Knowledge", tools: "Tools" };

function headers(json = true) {
    const base = state.token ? { Authorization: `Bearer ${state.token}` } : {};
    return json ? { ...base, "Content-Type": "application/json" } : base;
}

async function api(path, options = {}) {
    const res = await fetch(path, { ...options, headers: { ...headers(options.json !== false), ...(options.headers || {}) } });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Request failed");
    return data;
}

function showMessage(element, text, kind = "") {
    element.textContent = text;
    element.className = `message ${kind}`;
}

function showApp() {
    $("authView").classList.add("hidden");
    $("appView").classList.remove("hidden");
}

function showAuth() {
    $("appView").classList.add("hidden");
    $("authView").classList.remove("hidden");
}

function showPage(name) {
    pages.forEach((page) => page.classList.toggle("hidden", page.id !== name));
    menuItems.forEach((item) => item.classList.toggle("active", item.dataset.page === name));
    $("pageTitle").textContent = titles[name] || "LifeOS";
    if (name === "knowledge") loadDocuments();
    if (name === "tasks") loadTasks();
    if (name === "dashboard" || name === "tools") loadStatus();
}

async function authenticate(mode) {
    const payload = { email: $("authEmail").value, password: $("authPassword").value };
    const data = await api(`/api/auth/${mode}`, { method: "POST", body: JSON.stringify(payload) });
    state.token = data.token;
    state.user = data.user;
    localStorage.setItem("lifeos_token", state.token);
    $("userEmail").textContent = state.user.email;
    showApp();
    await loadStatus();
}

async function bootstrap() {
    if (!state.token) return showAuth();
    try {
        const data = await api("/api/auth/me");
        state.user = data.user;
        $("userEmail").textContent = state.user.email;
        showApp();
        await loadStatus();
    } catch {
        localStorage.removeItem("lifeos_token");
        state.token = null;
        showAuth();
    }
}

async function loadStatus() {
    const status = await api("/api/status");
    $("docCount").textContent = status.documents;
    $("taskCount").textContent = status.tasks;
    $("gmailStatus").textContent = status.gmail_connected ? "On" : "Off";
    $("calendarStatus").textContent = status.calendar_connected ? "On" : "Off";
    $("gmailToggle").checked = status.gmail_connected;
    $("calendarToggle").checked = status.calendar_connected;
    $("connectGoogleBtn").disabled = !status.google_credentials_available;
    showMessage($("googleCredsMessage"), status.google_credentials_available ? "Google OAuth credentials found." : "Add client_secrets.json to enable Google OAuth.");
}

function addChat(role, text) {
    const item = document.createElement("div");
    item.className = `chat-message ${role}`;
    item.textContent = text;
    $("chatLog").appendChild(item);
    $("chatLog").scrollTop = $("chatLog").scrollHeight;
}

async function askAgent(question) {
    addChat("user", question);
    addChat("assistant", "Thinking...");
    const pending = $("chatLog").lastElementChild;
    try {
        const data = await api("/api/ask", { method: "POST", body: JSON.stringify({ question }) });
        pending.textContent = data.answer;
        await loadStatus();
    } catch (err) {
        pending.textContent = err.message;
    }
}

async function loadTasks() {
    const data = await api("/api/tasks");
    const list = $("taskList");
    list.innerHTML = "";
    if (!data.tasks.length) list.innerHTML = '<p class="muted">No tasks yet. Ask the agent to add one.</p>';
    data.tasks.forEach((task) => {
        const row = document.createElement("div");
        row.className = "list-row";
        row.innerHTML = `<span>${task.completed ? "Done" : "Open"} · ${task.title}</span><button class="secondary">Remove</button>`;
        row.querySelector("button").addEventListener("click", async () => { await api(`/api/tasks/${task.id}`, { method: "DELETE" }); loadTasks(); loadStatus(); });
        list.appendChild(row);
    });
}

async function loadDocuments() {
    const data = await api("/api/documents");
    const list = $("documentList");
    list.innerHTML = "";
    if (!data.documents.length) list.innerHTML = '<p class="muted">No documents uploaded.</p>';
    data.documents.forEach((doc) => {
        const row = document.createElement("div");
        row.className = "list-row";
        row.innerHTML = `<span>${doc.filename} · ${doc.chunks} chunks</span><button class="secondary">Remove</button>`;
        row.querySelector("button").addEventListener("click", async () => { await api(`/api/documents/${encodeURIComponent(doc.filename)}`, { method: "DELETE" }); loadDocuments(); loadStatus(); });
        list.appendChild(row);
    });
}

async function uploadDocument() {
    const file = $("documentInput").files[0];
    if (!file) return;
    const form = new FormData();
    form.append("file", file);
    const res = await fetch("/api/documents", { method: "POST", headers: headers(false), body: form });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || "Upload failed");
    $("documentInput").value = "";
    await loadDocuments();
    await loadStatus();
}

async function searchDocuments(query) {
    const data = await api("/api/documents/search", { method: "POST", body: JSON.stringify({ query, k: 5 }) });
    const box = $("searchResults");
    box.innerHTML = "";
    if (!data.results.length) box.innerHTML = '<p class="muted">No matching chunks found.</p>';
    data.results.forEach((result) => {
        const item = document.createElement("article");
        item.className = "result-item";
        item.innerHTML = `<strong>${result.source} · page ${result.page}</strong><p>${result.content}</p>`;
        box.appendChild(item);
    });
}

async function setConnections() {
    try {
        await api("/api/connections", {
            method: "POST",
            body: JSON.stringify({ gmail_enabled: $("gmailToggle").checked, calendar_enabled: $("calendarToggle").checked }),
        });
    } catch (err) {
        alert(err.message);
    }
    await loadStatus();
}

$("authForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { await authenticate("login"); } catch (err) { showMessage($("authMessage"), err.message, "error"); }
});

$("registerBtn").addEventListener("click", async () => {
    try { await authenticate("register"); } catch (err) { showMessage($("authMessage"), err.message, "error"); }
});

$("logoutBtn").addEventListener("click", async () => {
    try { await api("/api/auth/logout", { method: "POST" }); } catch {}
    localStorage.removeItem("lifeos_token");
    state.token = null;
    showAuth();
});

menuItems.forEach((item) => item.addEventListener("click", () => showPage(item.dataset.page)));
$("chatForm").addEventListener("submit", (event) => { event.preventDefault(); const q = $("questionInput").value.trim(); if (q) askAgent(q); $("questionInput").value = ""; });
$("refreshTasksBtn").addEventListener("click", loadTasks);
$("uploadForm").addEventListener("submit", async (event) => { event.preventDefault(); try { await uploadDocument(); } catch (err) { alert(err.message); } });
$("searchForm").addEventListener("submit", (event) => { event.preventDefault(); searchDocuments($("searchInput").value); });
$("gmailToggle").addEventListener("change", setConnections);
$("calendarToggle").addEventListener("change", setConnections);
$("connectGoogleBtn").addEventListener("click", async () => { const data = await api("/api/google/connect"); window.location.href = data.url; });
$("disconnectGoogleBtn").addEventListener("click", async () => { await api("/api/google", { method: "DELETE" }); await loadStatus(); });

bootstrap();
