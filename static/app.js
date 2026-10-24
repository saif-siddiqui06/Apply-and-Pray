// Apply & Pray dashboard. Talks only to the local server (app.py), with the page's token.
"use strict";

const TOKEN = document.querySelector('meta[name="app-token"]').content;
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

// Everything that comes from websites (job titles, companies...) is escaped before it goes into the page
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const safeUrl = (url) => (/^https?:\/\//i.test(url || "") ? url : "");
const link = (url, text) => (safeUrl(url) ? `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : "");

async function api(path, options = {}) {
  const headers = { "X-Token": TOKEN, ...(options.json !== undefined ? { "Content-Type": "application/json" } : {}) };
  const response = await fetch(path, { method: options.method || (options.json !== undefined || options.body ? "POST" : "GET"), headers,
                                       body: options.json !== undefined ? JSON.stringify(options.json) : options.body });
  const isJson = (response.headers.get("Content-Type") || "").includes("json");
  const data = isJson ? await response.json() : await response.text();
  if (!response.ok) throw Object.assign(new Error((data && data.error) || `Error ${response.status}`), { data, status: response.status });
  return data;
}

let toastTimer;
function toast(message) {
  const box = $("#toast");
  box.textContent = message;
  box.classList.remove("hidden");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => box.classList.add("hidden"), 3500);
}

// ---------- Tabs ----------
let currentTab = "setup";
function showTab(name) {
  currentTab = name;
  $$(".tab").forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === name));
  $$(".page").forEach((page) => page.classList.toggle("hidden", page.id !== `tab-${name}`));
  try { localStorage.setItem("tab", name); } catch (e) { /* storage blocked: fine */ }
  if (name === "setup") loadSetup();
  if (name === "run") { loadSetup(false); refreshRun(); }
  if (name === "applications") loadApplications();
  if (name === "review") loadReview();
  if (name === "people") loadPeople();
}
$$(".tab").forEach((tab) => tab.addEventListener("click", () => showTab(tab.dataset.tab)));

// ---------- Setup ----------
let overview = null;
let openStep = null;
const checking = {};   // step id -> true while its check runs

async function loadSetup(render = true) {
  overview = await api("/api/setup");
  if (render) renderSetup();
  renderModes();
}

function renderSetup() {
  const { steps, features, done, total } = overview;
  $("#progress-label").textContent = done === total ? "All steps done 🎉" : `${done} of ${total} steps done`;
  $("#progress-bar").style.width = `${(done / total) * 100}%`;

  $("#features").innerHTML = features.map((f) => {
    let badge, need = "";
    if (!f.ready) { badge = `<span class="badge soon">Coming soon</span>`; need = f.unlocked ? "Your setup is ready for it." : `Needs: ${f.missing.join(", ")}`; }
    else if (f.unlocked) badge = `<span class="badge ok">✓ Unlocked</span>`;
    else { badge = `<span class="badge lock">🔒 Locked</span>`; need = `Needs: ${f.missing.join(", ")}`; }
    return `<div class="feature"><div class="name">${esc(f.title)} ${badge}</div><div class="about">${esc(f.about)}</div>${need ? `<div class="need">${esc(need)}</div>` : ""}</div>`;
  }).join("");

  if (openStep === null) openStep = (steps.find((s) => !s.state.done) || {}).id || null;
  const container = $("#steps");
  container.innerHTML = "";
  steps.forEach((step) => container.appendChild(renderStep(step)));
}

function stepBadge(step) {
  if (checking[step.id]) return `<span class="badge soon">Checking…</span>`;
  if (step.state.done) return `<span class="badge ok">✓ Done</span>`;
  return `<span class="badge lock">To do</span>`;
}

function renderStep(step) {
  const box = document.createElement("div");
  box.className = "step" + (openStep === step.id ? " open" : "");
  box.innerHTML = `
    <button class="step-head" type="button"><span class="step-icon">${step.icon}</span><span class="step-title">${esc(step.title)}</span>${stepBadge(step)}<span class="chev">›</span></button>
    <div class="step-body ${openStep === step.id ? "" : "hidden"}">
      <p class="why">${esc(step.why)}</p>
      ${step.guide ? `<details class="guide" ${step.state.done ? "" : "open"}><summary>How to</summary>${step.guide}</details>` : ""}
      <form class="form" novalidate></form>
      <div class="step-actions"></div>
      <div class="step-result"></div>
    </div>`;
  $(".step-head", box).addEventListener("click", () => { openStep = openStep === step.id ? null : step.id; renderSetup(); });

  const form = $("form", box);
  step.fields.forEach((field) => form.appendChild(renderField(field, step)));
  applyShowIf(form, step);
  form.addEventListener("change", () => applyShowIf(form, step));
  form.addEventListener("submit", (e) => e.preventDefault());

  const actions = $(".step-actions", box);
  if (step.fields.length) {
    const save = button(step.check ? "Save and test" : "Save", "primary", () => saveStep(step, form, box));
    actions.appendChild(save);
  } else if (step.check) {
    actions.appendChild(button(step.id === "linkedin" ? "Open LinkedIn" : "Test", "primary", () => runCheck(step.id)));
  }
  if (step.check && step.fields.length && step.state.missing.length === 0) actions.appendChild(button("Test again", "", () => runCheck(step.id)));

  const result = $(".step-result", box);
  if (checking[step.id]) {
    result.innerHTML = `<div class="result wait">${step.id === "linkedin" ? "A Chrome window opened: log in to LinkedIn there. This turns green when your feed shows." : "Checking…"}</div>`;
  } else if (step.state.check) {
    const c = step.state.check;
    result.innerHTML = `<div class="result ${c.ok ? "ok" : "bad"}">${c.ok ? "✓" : "✗"} ${esc(c.detail)}${c.at ? ` <span class="muted">(${esc(c.at)})</span>` : ""}</div>`;
  }
  if (!step.state.done && step.state.missing.length) {
    result.insertAdjacentHTML("beforeend", `<div class="help muted" style="margin-top:8px">Still needed: ${esc(step.state.missing.join(", "))}</div>`);
  }
  return box;
}

function button(text, kind, onClick) {
  const b = document.createElement("button");
  b.type = "button";
  b.className = `btn ${kind}`;
  b.textContent = text;
  b.addEventListener("click", onClick);
  return b;
}

function renderField(field, step) {
  const wrap = document.createElement("div");
  const wide = ["textarea", "list", "resume", "multiselect", "checkbox"].includes(field.type);
  wrap.className = "field" + (wide ? " wide" : "");
  wrap.dataset.name = field.name;
  const id = `f-${step.id}-${field.name}`;
  const required = field.required ? ` <span class="req">*</span>` : "";
  const help = field.help ? `<span class="help">${esc(field.help)}</span>` : "";
  const placeholder = field.placeholder ? ` placeholder="${esc(field.placeholder)}"` : "";
  const value = field.value;

  if (field.type === "checkbox") {
    wrap.innerHTML = `<label class="checkbox"><input type="checkbox" id="${id}" ${value ? "checked" : ""}> ${esc(field.label)}</label>${help}`;
  } else if (field.type === "select") {
    const options = field.options.map((o) => (Array.isArray(o) ? o : [o, o]));
    wrap.innerHTML = `<label for="${id}">${esc(field.label)}${required}</label><select id="${id}">${options.map(([v, l]) => `<option value="${esc(v)}" ${String(value) === String(v) ? "selected" : ""}>${esc(l)}</option>`).join("")}</select>${help}`;
  } else if (field.type === "multiselect") {
    const chosen = Array.isArray(value) ? value : [];
    wrap.innerHTML = `<label>${esc(field.label)}${required}</label><div class="checks">${field.options.map((o) => `<label><input type="checkbox" value="${esc(o)}" ${chosen.includes(o) ? "checked" : ""}> ${esc(o)}</label>`).join("")}</div>${help}`;
  } else if (field.type === "textarea" || field.type === "list") {
    const text = field.type === "list" && Array.isArray(value) ? value.join("\n") : value;
    wrap.innerHTML = `<label for="${id}">${esc(field.label)}${required}</label><textarea id="${id}"${placeholder}>${esc(text)}</textarea>${help}`;
  } else if (field.type === "password") {
    const hint = field.is_set ? "Saved ✓  (leave empty to keep it)" : (field.placeholder || "");
    wrap.innerHTML = `<label for="${id}">${esc(field.label)}${required}</label><input type="password" id="${id}" autocomplete="new-password" placeholder="${esc(hint)}">${help}`;
  } else if (field.type === "resume") {
    const name = value ? String(value).split(/[\\/]/).pop() : "";
    const exists = step.state.missing.indexOf(field.label) === -1 && name;
    wrap.innerHTML = `<label for="${id}">${esc(field.label)}${required}</label>
      <div class="muted">${exists ? `Current: <b>${esc(name)}</b>` : "No resume yet."}</div>
      <input type="file" id="${id}" accept=".pdf,.docx"><div class="resume-out"></div>`;
    $("input", wrap).addEventListener("change", (e) => uploadResume(e.target, wrap));
  } else {
    const type = { email: "email", tel: "tel", url: "url", number: "number" }[field.type] || "text";
    wrap.innerHTML = `<label for="${id}">${esc(field.label)}${required}</label><input type="${type}" id="${id}" value="${esc(value)}"${placeholder}>${help}`;
  }
  return wrap;
}

function applyShowIf(form, step) {
  step.fields.forEach((field) => {
    if (!field.show_if) return;
    const [other, allowed] = field.show_if;
    const control = $(`[data-name="${other}"] select`, form);
    const wrap = $(`[data-name="${field.name}"]`, form);
    if (control && wrap) wrap.classList.toggle("hidden", !allowed.includes(control.value));
  });
}

function collect(form, step) {
  const values = {};
  step.fields.forEach((field) => {
    const wrap = $(`[data-name="${field.name}"]`, form);
    if (!wrap || field.type === "resume" || wrap.classList.contains("hidden")) return;
    if (field.type === "checkbox") values[field.name] = $("input", wrap).checked;
    else if (field.type === "multiselect") values[field.name] = $$("input:checked", wrap).map((i) => i.value);
    else values[field.name] = $("input, select, textarea", wrap).value;
  });
  return values;
}

async function saveStep(step, form, box) {
  $$(".field.invalid", form).forEach((f) => f.classList.remove("invalid"));
  try {
    overview = await api(`/api/setup/${step.id}`, { json: collect(form, step) });
    const saved = overview.steps.find((s) => s.id === step.id);
    if (step.check && saved.state.missing.length === 0) { renderSetup(); runCheck(step.id); return; }
    toast(saved.state.done ? `${step.title}: done ✓` : "Saved");
    if (saved.state.done) openStep = (overview.steps.find((s) => !s.state.done) || {}).id || null;
    renderSetup();
    renderModes();
  } catch (e) {
    if (e.data && e.data.field) {
      const wrap = $(`[data-name="${e.data.field}"]`, form);
      if (wrap) { wrap.classList.add("invalid"); $("input, select, textarea", wrap)?.focus(); }
    }
    $(".step-result", box).innerHTML = `<div class="result bad">${esc(e.message)}</div>`;
  }
}

async function uploadResume(input, wrap) {
  const file = input.files[0];
  if (!file) return;
  const body = new FormData();
  body.append("resume", file);
  const out = $(".resume-out", wrap);
  out.innerHTML = `<div class="result wait">Uploading…</div>`;
  try {
    const data = await api("/api/resume", { body });
    overview = data.overview;
    renderSetup();
    const fresh = $(`#steps [data-name="default_resume_path"] .resume-out`);
    if (fresh) fresh.innerHTML = data.preview
      ? `<div class="result ok">✓ Saved. The bot read this from it:</div><div class="preview">${esc(data.preview)}…</div>`
      : `<div class="result bad">${esc(data.warning)}</div>`;
  } catch (e) {
    out.innerHTML = `<div class="result bad">${esc(e.message)}</div>`;
  }
}

async function runCheck(stepId) {
  try {
    await api(`/api/check/${stepId}`, { json: {} });
  } catch (e) { toast(e.message); return; }
  checking[stepId] = true;
  renderSetup();
  const timer = setInterval(async () => {
    try {
      const state = await api(`/api/check/${stepId}`);
      if (state.running) return;
      clearInterval(timer);
      delete checking[stepId];
      await loadSetup();
      if (state.result) toast(state.result.ok ? "✓ " + state.result.detail : state.result.detail);
    } catch (e) { clearInterval(timer); delete checking[stepId]; }
  }, 2000);
}

// ---------- Run ----------
const MODES = [
  { id: "easy", title: "Easy Apply", about: "Applies inside LinkedIn.", needs: ["easy"] },
  { id: "normal", title: "Normal Apply", about: "Fills forms on company websites.", needs: ["normal"] },
  { id: "both", title: "Both", about: "Easy Apply jobs, then company websites.", needs: ["easy", "normal"] },
  { id: "feed", title: "Feed jobs", about: "Jobs posted in the LinkedIn feed: forms and emails.", needs: ["feed"] },
  { id: "connect", title: "Networking", about: "Checks who accepted, sends approved messages and connection requests.", needs: ["connect"] },
];
let selectedMode = null;
try { selectedMode = localStorage.getItem("mode"); } catch (e) { /* fine */ }

function renderModes() {
  if (!overview) return;
  const feature = (id) => overview.features.find((f) => f.id === id);
  $("#modes").innerHTML = MODES.map((m) => {
    const locked = m.needs.filter((id) => !feature(id).unlocked);
    const missing = [...new Set(locked.flatMap((id) => feature(id).missing))];
    return `<button type="button" class="mode ${selectedMode === m.id && !locked.length ? "selected" : ""}" data-mode="${m.id}" ${locked.length ? "disabled" : ""}>
      <b>${esc(m.title)}</b> ${locked.length ? `<span class="badge lock">🔒</span>` : ""}<div class="about">${esc(locked.length ? "Needs: " + missing.join(", ") : m.about)}</div></button>`;
  }).join("");
  $$("#modes .mode").forEach((b) => b.addEventListener("click", () => {
    selectedMode = b.dataset.mode;
    try { localStorage.setItem("mode", selectedMode); } catch (e) { /* fine */ }
    renderModes();
  }));
}

$("#start-btn").addEventListener("click", async () => {
  $("#run-error").textContent = "";
  if (!selectedMode || $(`#modes .mode[data-mode="${selectedMode}"]`)?.disabled) { $("#run-error").textContent = "Choose a mode first."; return; }
  try { renderRun(await api("/api/run/start", { json: { mode: selectedMode, test: $("#test-run").checked } })); startRunPolling(); }
  catch (e) { $("#run-error").textContent = e.message; }
});

$("#pause-btn").addEventListener("click", async () => {
  const paused = $("#pause-btn").dataset.paused === "1";
  try { renderRun(await api("/api/run/control", { json: { action: paused ? "resume" : "pause" } })); } catch (e) { toast(e.message); }
});
$$("[data-action]").forEach((b) => b.addEventListener("click", async () => {
  if (b.dataset.action === "quit" && !confirm("Quit the bot now? The current application is dropped.")) return;
  try { renderRun(await api("/api/run/control", { json: { action: b.dataset.action } })); toast({ skip: "Skipping this job", stop: "Stopping after this job", quit: "Quitting" }[b.dataset.action]); }
  catch (e) { toast(e.message); }
}));

const MODE_NAMES = { easy: "Easy Apply", normal: "Normal Apply", both: "Easy + Normal Apply", feed: "Feed jobs", connect: "Networking" };
function renderRun(state) {
  const card = $("#running-card");
  card.classList.toggle("hidden", !state.running && !state.started);
  $("#start-btn").disabled = state.running;
  if (state.running || state.started) {
    $("#run-dot").className = "dot" + (state.running ? (state.paused ? " paused" : "") : " off");
    $("#run-title").textContent = state.running
      ? `${state.paused ? "Paused" : state.stopping ? "Stopping after this job" : "Running"}: ${MODE_NAMES[state.mode] || ""}${state.test ? " · TEST RUN, nothing is sent" : ""} (since ${state.started})`
      : `Finished: ${MODE_NAMES[state.mode] || ""}`;
    $("#run-status").textContent = state.status || "";
    $("#pause-btn").textContent = state.paused ? "Resume" : "Pause";
    $("#pause-btn").dataset.paused = state.paused ? "1" : "0";
    $$("#running-card .btn").forEach((b) => (b.disabled = !state.running));
    const log = $("#run-log");
    const atBottom = log.scrollHeight - log.scrollTop - log.clientHeight < 40;
    log.textContent = state.log.join("\n");
    if (atBottom) log.scrollTop = log.scrollHeight;
  }
  renderTiles("#run-stats", state.stats);
}

let runTimer = null;
async function refreshRun() {
  try {
    const state = await api("/api/run");
    renderRun(state);
    if (state.running) startRunPolling();
    else if (runTimer) { clearInterval(runTimer); runTimer = null; }
  } catch (e) { /* server restarting */ }
}
function startRunPolling() { if (!runTimer) runTimer = setInterval(refreshRun, 2000); }

// ---------- Applications ----------
function renderTiles(selector, s) {
  if (!s) return;
  const tiles = [["Applied today", s.applied_today], ["Applied in total", s.applied_total], ["Easy Apply", s.easy], ["Normal Apply", s.normal],
                 ["Feed & email", s.feed], ["Apply by hand", s.apply_by_hand], ["To review", s.to_review], ["Failed today", s.failed_today]];
  setReviewBadge(s.to_review);
  $(selector).innerHTML = tiles.map(([label, n]) => `<div class="tile"><div class="num">${esc(n)}</div><div class="label">${esc(label)}</div></div>`).join("");
}

let applicationsData = null;
async function loadApplications() {
  applicationsData = await api("/api/applications");
  renderTiles("#app-stats", applicationsData.stats);
  renderHand();
  renderApplications();
}

function renderHand() {
  const rows = applicationsData.apply_by_hand;
  $("#hand-count").textContent = `(${rows.length})`;
  $("#hand-table").innerHTML = rows.length ? `<thead><tr><th>Job</th><th>Why</th><th>Added</th><th></th></tr></thead><tbody>${rows.slice(0, 300).map((r) => `
    <tr><td><b>${esc(r.title)}</b><div class="sub">${esc(r.company)}</div></td><td class="sub">${esc(r.reason)}</td><td class="sub date">${esc((r.added_at || "").slice(0, 10))}</td>
    <td><div class="actions">${link(r.apply_link, "Apply ↗")} ${link(r.job_link, "LinkedIn ↗")}<button class="btn small" data-applied="${esc(r.job_id)}">Mark applied</button></div></td></tr>`).join("")}</tbody>`
    : `<tbody><tr><td class="muted">Nothing to apply by hand. 🎉</td></tr></tbody>`;
  $$("#hand-table [data-applied]").forEach((b) => b.addEventListener("click", async () => {
    try { await api(`/api/applications/${encodeURIComponent(b.dataset.applied)}/applied`, { json: {} }); toast("Marked as applied"); loadApplications(); }
    catch (e) { toast(e.message); }
  }));
}

const METHOD = { easy: "Easy Apply", normal: "Normal Apply", link: "Link saved", feed: "Feed post", email: "Email" };
function renderApplications() {
  const search = $("#app-search").value.trim().toLowerCase();
  const filter = $("#app-filter").value;
  const rows = applicationsData.applications.filter((r) => (!filter || r.method === filter) &&
    (!search || `${r.title} ${r.company}`.toLowerCase().includes(search)));
  $("#app-table").innerHTML = `<thead><tr><th>Job</th><th>How</th><th>Date</th><th>Hiring contact</th><th></th></tr></thead><tbody>${rows.slice(0, 400).map((r) => `
    <tr><td><b>${esc(r.title)}</b><div class="sub">${esc(r.company)}${r.location ? " · " + esc(r.location) : ""}</div></td>
    <td>${esc(METHOD[r.method] || r.method)}${r.status === "link_saved" ? `<div class="sub">not applied yet</div>` : ""}</td>
    <td class="sub date">${esc(((r.applied_at || r.created_at) || "").slice(0, 10))}</td>
    <td>${r.hr_link ? link(r.hr_link, r.hr_name || "Profile") : `<span class="sub">-</span>`}</td>
    <td><div class="actions">${link(r.job_link, "LinkedIn ↗")} ${link(r.apply_link, "Company ↗")}</div></td></tr>`).join("")}</tbody>`
    + (rows.length > 400 ? `<tfoot><tr><td colspan="5" class="muted">Showing 400 of ${rows.length}. Use search, or Export CSV for all.</td></tr></tfoot>` : "");
}
$("#app-search").addEventListener("input", () => applicationsData && renderApplications());
$("#app-filter").addEventListener("change", () => applicationsData && renderApplications());

$$("[data-export]").forEach((b) => b.addEventListener("click", async () => {
  try {
    const response = await fetch(`/api/export/${b.dataset.export}.csv`, { headers: { "X-Token": TOKEN } });
    if (!response.ok) throw new Error(`Export failed (${response.status})`);
    const url = URL.createObjectURL(await response.blob());
    const a = Object.assign(document.createElement("a"), { href: url, download: `${b.dataset.export}.csv` });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (e) { toast(e.message); }
}));

// ---------- Review ----------
function setReviewBadge(count) {
  const badge = $("#review-badge");
  badge.textContent = count || "";
  badge.classList.toggle("hidden", !count);
}

// A post's own page when LinkedIn showed its id, else the author's recent posts (LinkedIn's search no longer shows post ids)
const postLink = (urn, authorUrl) => (urn || "").startsWith("urn:li:") ? `https://www.linkedin.com/feed/update/${urn}/`
  : (authorUrl ? authorUrl.replace(/\/$/, "") + "/recent-activity/all/" : "");

const ACTION_TAGS = {
  applied: ["Applied", "good"], email_sent: ["Emailed", "good"], email_drafted: ["Email to review", "wait"], saved_for_you: ["Saved for you", "wait"],
  lead: ["Saved for Networking", "wait"], apply_failed: ["Failed", "bad"], skipped: ["Skipped", ""],
};

async function loadReview() {
  const data = await api("/api/review");
  setReviewBadge(data.drafts.length + data.invites.filter((i) => i.status === "draft").length + data.messages.filter((i) => i.status === "draft").length);
  renderInvites(data);
  renderMessages(data);
  $("#review-info").innerHTML = (data.gmail_ready
    ? `Emails sent today: <b>${esc(data.sent_today)}</b> of ${esc(data.daily_limit)}.`
    : `<span class="error">Finish Setup → Gmail to send these.</span> You can still read and edit them.`)
    + (data.sent.length ? ` · Sent so far: ${esc(data.sent.length)}${data.sent.length >= 50 ? "+" : ""}.` : "");

  const drafts = $("#drafts");
  drafts.innerHTML = data.drafts.length ? "" : `<div class="card muted">Nothing to review. Run <b>Feed jobs</b> to find jobs posted as LinkedIn posts.</div>`;
  data.drafts.forEach((item) => {
    const box = document.createElement("div");
    box.className = "draft";
    const postUrn = (item.source || "").startsWith("feed:") ? item.source.slice(5) : "";
    box.innerHTML = `
      <div class="meta"><div>To: <span class="to">${esc(item.to_address)}</span>${item.to_name ? ` <span class="muted">(${esc(item.to_name)})</span>` : ""}</div>
        <div class="muted">${postUrn ? link(postLink(postUrn, item.to_name_url), "See the post ↗") : ""} · ${esc((item.created_at || "").slice(0, 16))}</div></div>
      <input type="text" class="subject" value="${esc(item.subject)}" aria-label="Subject">
      <textarea class="body" aria-label="Message">${esc(item.body)}</textarea>
      <div class="attach">${item.attachment ? `📎 ${esc(item.attachment.split(/[\/]/).pop())}` : "⚠️ No resume attached: add one in Setup → Your basics"}</div>
      ${item.error ? `<div class="result bad">${esc(item.error)}</div>` : ""}
      <div class="step-actions"></div>`;
    const actions = $(".step-actions", box);
    const send = button("Approve and send", "primary", () => reviewAction(item.id, "send", box));
    send.disabled = !data.gmail_ready;
    actions.append(send, button("Save edits", "", () => reviewAction(item.id, "save", box)), button("Skip", "", () => reviewAction(item.id, "skip", box)));
    drafts.appendChild(box);
  });

  $("#posts-count").textContent = `(${data.posts.length})`;
  $("#posts-table").innerHTML = data.posts.length ? `<thead><tr><th>Post</th><th>What the bot did</th><th>Date</th><th></th></tr></thead><tbody>${data.posts.map((p) => {
    const [label, kind] = ACTION_TAGS[p.action] || [p.action, ""];
    return `<tr><td><b>${esc(p.role)}</b><div class="sub">${esc(p.author)}</div></td>
      <td><span class="action-tag ${kind}">${esc(label)}</span><div class="sub">${esc(p.detail)}</div></td>
      <td class="sub date">${esc((p.seen_at || "").slice(0, 10))}</td>
      <td><div class="actions">${link(postLink(p.urn, p.author_url), "Post ↗")} ${link(p.apply_link, "Link ↗")}</div></td></tr>`;
  }).join("")}</tbody>` : `<tbody><tr><td class="muted">No feed posts read yet.</td></tr></tbody>`;
}

function renderInvites(data) {
  const drafts = data.invites.filter((i) => i.status === "draft"), approved = data.invites.filter((i) => i.status === "approved");
  const l = data.invite_limits;
  $("#invites-count").textContent = `(${drafts.length} to review, ${approved.length} approved)`;
  $("#invite-info").innerHTML = data.networking_ready
    ? `Sent today: <b>${esc(l.today)}</b> · this week: <b>${esc(l.week)}</b> · notes left this month: <b>${esc(data.notes_left)}</b>.`
      + (l.reason ? ` <span class="error">${esc(l.reason)}</span>` : "") + ` Approved requests are sent when you run <b>Networking</b>.`
    : `<span class="error">Finish Setup → Networking first.</span>`;
  $("#find-people").disabled = !data.networking_ready;
  $("#approve-all").disabled = !drafts.length;
  const box = $("#invites");
  box.innerHTML = data.invites.length ? "" : `<div class="card muted">No requests yet. Click <b>Find people to connect with</b>: it uses the hiring contacts of jobs you applied to, and people whose job posts said "DM me".</div>`;
  data.invites.forEach((item) => {
    const card = document.createElement("div");
    card.className = "draft";
    const why = item.source === "hirer" ? `Posted the job you applied to: <b>${esc(item.subject)}</b>${item.company ? " @ " + esc(item.company) : ""}`
                                         : `Posted about <b>${esc(item.subject)}</b> and asked people to reach out`;
    card.innerHTML = `
      <div class="meta"><div><span class="to">${link(item.to_address, item.to_name || "Profile") || esc(item.to_name || "")}</span>${item.headline ? ` <span class="muted">· ${esc(item.headline)}</span>` : ""}</div>
        <div>${item.status === "approved" ? `<span class="action-tag good">Approved: sent on the next run</span>` : ""}</div></div>
      <div class="muted" style="font-size:14px;margin-bottom:8px">${why} ${link(item.job_link, "↗")}</div>
      <textarea class="body note" aria-label="Note" placeholder="No note: the request is sent without one (your notes this month are used up, or add one here)">${esc(item.body)}</textarea>
      <div class="counter"></div>
      ${item.error ? `<div class="result bad">${esc(item.error)}</div>` : ""}
      <div class="step-actions"></div>`;
    const area = $("textarea", card), counter = $(".counter", card);
    const count = () => { counter.textContent = `${area.value.length} / ${data.note_limit}`; counter.classList.toggle("over", area.value.length > data.note_limit); };
    area.addEventListener("input", count); count();
    const actions = $(".step-actions", card);
    if (item.status === "draft") actions.append(button("Approve", "primary", () => reviewAction(item.id, "approve", card)));
    actions.append(button("Save edits", "", () => reviewAction(item.id, "save", card)), button("Skip", "", () => reviewAction(item.id, "skip", card)));
    box.appendChild(card);
  });
}

function renderMessages(data) {
  const drafts = data.messages.filter((i) => i.status === "draft"), approved = data.messages.filter((i) => i.status === "approved");
  const l = data.message_limits;
  $("#messages-count").textContent = `(${drafts.length} to review, ${approved.length} approved)`;
  $("#message-info").innerHTML = `To people who accepted your request. Sent today: <b>${esc(l.today)}</b>.` + (l.reason ? ` <span class="error">${esc(l.reason)}</span>` : "")
    + ` Before a follow-up, the bot checks the conversation: if they replied, it isn't sent.`;
  $("#approve-all-messages").disabled = !drafts.length;
  const box = $("#messages");
  box.innerHTML = data.messages.length ? "" : `<div class="card muted">No messages yet. They're written when someone accepts your connection request (checked on each <b>Networking</b> run).</div>`;
  data.messages.forEach((item) => {
    const card = document.createElement("div");
    card.className = "draft";
    const kind = item.role_key === "follow_up" ? "Follow-up" : "First message";
    card.innerHTML = `
      <div class="meta"><div><span class="kind-tag">${kind}</span><span class="to">${link(item.to_address, item.to_name || "Profile") || esc(item.to_name || "")}</span>${item.headline ? ` <span class="muted">· ${esc(item.headline)}</span>` : ""}</div>
        <div>${item.status === "approved" ? `<span class="action-tag good">Approved: sent on the next run</span>` : ""}</div></div>
      <div class="muted" style="font-size:14px;margin-bottom:8px">${item.subject ? `About <b>${esc(item.subject)}</b>${item.company ? " @ " + esc(item.company) : ""}` : ""} ${link(item.job_link, "↗")}</div>
      <textarea class="body" aria-label="Message">${esc(item.body)}</textarea>
      <div class="counter"></div>
      ${item.error ? `<div class="result bad">${esc(item.error)}</div>` : ""}
      <div class="step-actions"></div>`;
    const area = $("textarea", card), counter = $(".counter", card);
    const count = () => { counter.textContent = `${area.value.length} / ${data.message_limit}`; counter.classList.toggle("over", area.value.length > data.message_limit); };
    area.addEventListener("input", count); count();
    const actions = $(".step-actions", card);
    if (item.status === "draft") actions.append(button("Approve", "primary", () => reviewAction(item.id, "approve", card)));
    actions.append(button("Save edits", "", () => reviewAction(item.id, "save", card)), button("Skip", "", () => reviewAction(item.id, "skip", card)));
    box.appendChild(card);
  });
}

$("#approve-all-messages").addEventListener("click", async () => {
  if (!confirm("Approve all messages waiting here? They're sent on the next Networking run, within your daily limit.")) return;
  try { toast((await api("/api/connect/approve-all", { json: { kind: "message" } })).detail); await loadReview(); } catch (e) { toast(e.message); }
});

// ---------- People ----------
const PEOPLE_STATUS = {
  new: ["Found: request next", "wait"], invite_drafted: ["Request to review", "wait"], invite_approved: ["Request approved", "wait"], invited: ["Request sent", ""], connected: ["Connected", "good"],
  messaged: ["Messaged", "good"], replied: ["Replied: your turn", "good"], skipped: ["Skipped", ""], failed: ["Couldn't reach", "bad"],
};
let peopleData = null;
async function loadPeople() {
  peopleData = await api("/api/people");
  const c = peopleData.counts, n = (k) => c[k] || 0;
  const tiles = [["Requests to review", n("invite_drafted") + n("invite_approved")], ["Requests sent", n("invited")], ["Connected", n("connected")],
                 ["Messaged", n("messaged")], ["Replied: your turn", n("replied")]];
  $("#people-stats").innerHTML = tiles.map(([label, num]) => `<div class="tile"><div class="num">${esc(num)}</div><div class="label">${esc(label)}</div></div>`).join("");
  const filter = $("#people-filter"), chosen = filter.value;
  filter.innerHTML = `<option value="">All (${peopleData.people.length})</option>` + Object.entries(PEOPLE_STATUS).filter(([k]) => c[k]).map(([k, [label]]) => `<option value="${k}">${esc(label)} (${c[k]})</option>`).join("");
  filter.value = chosen;
  renderPeople();
}
function renderPeople() {
  const chosen = $("#people-filter").value;
  const rows = peopleData.people.filter((p) => !chosen || p.status === chosen)
    .sort((a, b) => (b.status === "replied") - (a.status === "replied"));
  $("#people-table").innerHTML = rows.length ? `<thead><tr><th>Person</th><th>Why</th><th>Status</th><th>Last step</th></tr></thead><tbody>${rows.slice(0, 500).map((p) => {
    const [label, kind] = PEOPLE_STATUS[p.status] || [p.status, ""];
    const last = p.last_message_at || p.connected_at || p.invited_at || p.created_at || "";
    return `<tr class="${p.status === "replied" ? "your-turn" : ""}"><td>${link(p.profile_url, p.name || "Profile") || esc(p.name || "")}<div class="sub">${esc(p.headline || "")}</div></td>
      <td><b>${esc(p.role || "")}</b><div class="sub">${esc(p.company || (p.source === "feed" ? "Their job post" : ""))}${{recruiter: " · recruiter", alumni: " · alumni", hirer: " · posted the job"}[p.source] || ""}</div></td>
      <td><span class="action-tag ${kind}">${esc(label)}</span>${p.follow_ups ? `<div class="sub">follow-up sent</div>` : ""}<div class="sub">${esc(p.detail || "")}</div></td>
      <td class="sub date">${esc(last.slice(0, 16))}</td></tr>`;
  }).join("")}</tbody>` : `<tbody><tr><td class="muted">Nobody yet. Review → <b>Find people to connect with</b>.</td></tr></tbody>`;
}
$("#people-filter").addEventListener("change", () => peopleData && renderPeople());

$("#find-people").addEventListener("click", async (e) => {
  const b = e.target; b.disabled = true; const label = b.textContent; b.textContent = "Finding people and writing notes…";
  try {
    const r = await api("/api/connect/find", { json: {} });
    const m = r.messages || {};
    const parts = [r.found ? `${r.found} new request(s), ${r.with_note} with a note` : "", m.first ? `${m.first} message(s)` : "", m.follow_up ? `${m.follow_up} follow-up(s)` : ""].filter(Boolean);
    toast(parts.length ? parts.join(" · ") : "No new people or messages."); await loadReview();
  }
  catch (err) { toast(err.message); }
  b.textContent = label; b.disabled = false;
});
$("#approve-all").addEventListener("click", async () => {
  if (!confirm("Approve all connection requests waiting here? They're sent on the next Connections run, within your limits.")) return;
  try { toast((await api("/api/connect/approve-all", { json: {} })).detail); await loadReview(); } catch (e) { toast(e.message); }
});

async function reviewAction(id, action, box) {
  const subject = $(".subject", box) ? $(".subject", box).value : undefined, body = $(".body", box).value;
  $$("button", box).forEach((b) => (b.disabled = true));
  try {
    const result = await api(`/api/review/${id}`, { json: { action, subject, body } });
    toast(result.detail);
    await loadReview();
  } catch (e) {
    toast((e.data && e.data.detail) || e.message);
    $$("button", box).forEach((b) => (b.disabled = false));
  }
}

// ---------- Start ----------
let firstTab = "setup";
try { firstTab = localStorage.getItem("tab") || "setup"; } catch (e) { /* fine */ }
showTab(["setup", "run", "review", "people", "applications"].includes(firstTab) ? firstTab : "setup");
refreshRun();
