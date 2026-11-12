const state = { result: null, tab: "overview", reviews: {}, busy: false, currentRunId: null, currentProjectId: localStorage.getItem("scenarioStudioProject") || "" };
const $ = (selector) => document.querySelector(selector);
const form = $("#brief-form");
const criteriaInput = $("#criteria");
const output = $("#output-content");
let toastTimer;

function esc(value) { return String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;", "'":"&#39;"}[c])); }
function notify(message) { const toast = $("#toast"); toast.textContent = message; toast.classList.add("show"); clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("show"), 2200); }
function criteriaLines() { return criteriaInput.value.split("\n").map((line) => line.trim()).filter(Boolean); }
function inputPayload() { return {projectId: state.currentProjectId, product: $("#product").value, url: $("#url").value, feature: $("#feature").value, story: $("#story").value, criteria: criteriaLines()}; }

async function loadProjects(preferredId = "") {
  const response = await fetch("/api/projects");
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not load saved projects.");
  const select = $("#project-select");
  select.innerHTML = data.projects.map((project) => `<option value="${esc(project.id)}">${esc(project.name)}</option>`).join("");
  const wanted = preferredId || state.currentProjectId;
  state.currentProjectId = data.projects.some((project) => project.id === wanted) ? wanted : data.projects[0]?.id || "";
  select.value = state.currentProjectId;
  if (state.currentProjectId) localStorage.setItem("scenarioStudioProject", state.currentProjectId);
  await loadHistory();
}

async function loadHistory() {
  if (!state.currentProjectId) return;
  const response = await fetch(`/api/projects/${encodeURIComponent(state.currentProjectId)}/runs`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not load saved plans.");
  const history = $("#memory-history");
  if (!data.runs.length) { history.innerHTML = "<span>No saved plans yet. Generate a plan to start project memory.</span>"; return; }
  history.innerHTML = data.runs.map((run) => `<button type="button" class="history-item" data-run-id="${esc(run.runId)}"><span class="history-title">v${run.version} · ${esc(run.feature)}</span><span class="history-meta">${run.coverage}% · ${run.reviewedCount} reviewed</span></button>`).join("");
}

function clearCurrentResult() {
  state.result = null; state.reviews = {}; state.currentRunId = null; state.tab = "overview";
  $("#results-title").textContent = "Your reviewable output";
  $("#copy-output").disabled = true; $("#export-output").disabled = true;
  output.innerHTML = `<div class="empty-state"><div class="empty-icon">✳</div><h3>Make the requirements testable.</h3><p>Start with the sample or enter a synthetic story. Saved plans stay in the selected project.</p><div class="empty-flow"><span>Story</span><b>→</b><span>Scenarios</span><b>→</b><span>Saved memory</span></div></div>`;
}

async function loadRun(runId) {
  const response = await fetch(`/api/runs/${encodeURIComponent(runId)}`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not open this saved plan.");
  state.currentRunId = data.runId; state.currentProjectId = data.projectId; state.result = data.result;
  state.reviews = Object.fromEntries(data.result.criteria.map((criterion) => [criterion.id, data.reviews[criterion.id] || "pending"]));
  for (const key of ["product", "url", "feature", "story"]) $("#" + key).value = data.payload[key] || "";
  criteriaInput.value = data.payload.criteria.map((criterion) => typeof criterion === "string" ? criterion : `${criterion.id} | ${criterion.text}`).join("\n");
  $("#results-title").textContent = data.result.feature;
  $("#copy-output").disabled = false; $("#export-output").disabled = false;
  updateMetrics(); setTab("overview"); render();
  notify(`Opened saved plan v${data.version}`);
}

async function createProject() {
  const name = $("#new-project-name").value.trim();
  if (!name) { notify("Enter a project name first."); return; }
  const response = await fetch("/api/projects", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({name})});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not create the project.");
  $("#new-project-name").value = ""; $("#new-project-form").hidden = true;
  clearCurrentResult(); await loadProjects(data.project.id); notify("Project created and saved on this computer");
}

async function exportMemory() {
  if (!state.currentProjectId) return;
  const response = await fetch(`/api/projects/${encodeURIComponent(state.currentProjectId)}/export`);
  const bundle = await response.json();
  if (!response.ok) throw new Error(bundle.error || "Could not export project memory.");
  const blob = new Blob([JSON.stringify(bundle, null, 2)], {type:"application/json"});
  const url = URL.createObjectURL(blob); const a = document.createElement("a");
  a.href = url; a.download = `${bundle.project.name.toLowerCase().replace(/[^a-z0-9]+/g,"-")}-memory.json`; a.click(); URL.revokeObjectURL(url);
  notify("Saved plans backup downloaded");
}

async function importMemory(file) {
  if (!file) return;
  const bundle = JSON.parse(await file.text());
  const response = await fetch("/api/projects/import", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(bundle)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Could not import this project file.");
  clearCurrentResult(); await loadProjects(data.project.id); notify("Backup loaded as a new project");
}

async function loadExample() {
  const response = await fetch("/examples/saucedemo-checkout.json");
  if (!response.ok) throw new Error("Could not load the sample brief.");
  const example = await response.json();
  for (const key of ["product", "url", "feature", "story"]) $("#" + key).value = example[key];
  criteriaInput.value = example.criteria.join("\n");
  notify("SauceDemo checkout example loaded");
}

async function refreshStatus() {
  try {
    const response = await fetch("/api/status"); const info = await response.json();
    $("#engine-status").textContent = info.aiConfigured ? "AI + GUARDRAILS" : "LOCAL DEMO";
    $("#engine-caption").textContent = info.aiConfigured ? "AI mode sends this brief and approved project examples to OpenAI." : "Local rules mode · saved project stays on this computer";
    $(".pulse-dot").style.background = info.aiConfigured ? "#8978bd" : "#54a982";
  } catch { $("#engine-status").textContent = "LOCAL DEMO"; }
}

async function generate(event) {
  event.preventDefault();
  if (state.busy) return;
  const payload = inputPayload();
  if (!payload.projectId) { notify("Choose a project before generating."); return; }
  if (!payload.story.trim() || !payload.criteria.length) { notify("Add a user story and at least one acceptance criterion."); return; }
  setBusy(true);
  try {
    const response = await fetch("/api/generate", {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || "Generation failed.");
    state.result = result; state.currentRunId = result.memory?.runId || null; state.reviews = Object.fromEntries(result.criteria.map((c) => [c.id, "pending"])); state.tab = "overview";
    $("#results-title").textContent = result.feature;
    $("#copy-output").disabled = false; $("#export-output").disabled = false;
    updateMetrics(); setTab("overview"); render();
    await loadHistory();
    if (result.aiWarning) notify(result.aiWarning); else notify(`Plan saved as v${result.memory.version}`);
  } catch (error) { notify(error.message); }
  finally { setBusy(false); }
}
function setBusy(value) { state.busy = value; const button = $(".generate-button"); button.disabled = value; button.querySelector("span:first-child").textContent = value ? "Building your test plan…" : "Generate QA artifacts"; }
function updateMetrics() {
  const r = state.result;
  if (!r) return;
  const risk = r.riskSummary;
  $("#metrics").innerHTML = `<div class="metric"><span class="metric-label">CRITERIA COVERED</span><strong>${r.coverage}<small>%</small></strong><span class="metric-foot">${r.traceability.filter(x=>x.covered).length} / ${r.criteria.length} mapped</span></div><div class="metric"><span class="metric-label">RISK FLAGS</span><strong>${r.scenarios.length}</strong><span class="metric-foot">${risk.High} high · ${risk.Medium} med · ${risk.Low} low</span></div><div class="metric"><span class="metric-label">OPEN QUESTIONS</span><strong>${r.ambiguities.length}</strong><span class="metric-foot">needs clarification</span></div><div class="metric engine-metric"><span class="metric-label">GENERATOR</span><strong>${r.engine.includes("OpenAI")?"AI + rules":"Local rules"}</strong><span class="metric-foot">${r.scenarios.length} scenario drafts</span></div>`;
  $("#scenario-count").textContent = r.scenarios.length;
}
function setTab(tab) { state.tab = tab; document.querySelectorAll(".tab").forEach((button) => { const active = button.dataset.tab === tab; button.classList.toggle("active", active); button.setAttribute("aria-selected", active ? "true" : "false"); }); }
function render() {
  if (!state.result) return;
  const r = state.result;
  if (r.aiWarning) { output.innerHTML = `<div class="notice">${esc(r.aiWarning)}</div>` + renderTab(r); return; }
  output.innerHTML = renderTab(r);
}
function renderTab(r) {
  if (state.tab === "gherkin") return `<div class="section-caption"><h3>Feature file draft</h3><span>${r.scenarios.length} SCENARIOS · ${r.criteria.length} CRITERIA</span></div><div class="code-block"><span class="code-lang">GHERKIN</span><pre>${esc(r.gherkin)}</pre></div>`;
  if (state.tab === "cypress") return `<div class="notice">Starting point only. The studio does not crawl the target. Review locators, preconditions, and product rules before running.</div><div class="section-caption"><h3>Cypress spec skeleton</h3><span>JAVASCRIPT</span></div><div class="code-block"><span class="code-lang">CYPRESS</span><pre>${esc(r.cypress)}</pre></div>`;
  if (state.tab === "review") return renderReview(r);
  return renderOverview(r);
}
function riskClass(level) { return "risk-" + level.toLowerCase(); }
function renderOverview(r) {
  const rows = r.scenarios.map((s) => `<tr><td><span class="trace-id">${esc(s.id)}</span><span class="scenario-sub">${s.acceptanceIds.map(esc).join(", ")}</span></td><td><span class="scenario-title">${esc(s.title)}</span><span class="scenario-sub">${esc(s.expectedResult)}</span></td><td><span class="risk-badge ${riskClass(s.risk.level)}">${esc(s.risk.level.toUpperCase())}</span><span class="scenario-sub">score ${esc(s.risk.score)}</span></td><td><span class="kind-badge">${esc(s.kind)}</span></td><td><span class="review-badge ${state.reviews[s.acceptanceIds[0]] === "approved" ? "review-approved" : state.reviews[s.acceptanceIds[0]] === "changes" ? "review-changes" : ""}">${state.reviews[s.acceptanceIds[0]] === "approved" ? "Reviewed" : state.reviews[s.acceptanceIds[0]] === "changes" ? "Needs changes" : "Pending"}</span></td></tr>`).join("");
  const ambiguity = r.ambiguities.length ? `<div class="ambiguity-list">${r.ambiguities.map((a) => `<article class="ambiguity-card"><h4><span class="trace-id">${esc(a.criterionId)}</span> · ${esc(a.severity)}</h4><p>${esc(a.text)}</p>${a.reasons.map((reason) => `<p>↳ ${esc(reason)}</p>`).join("")}<p class="question">Question for the product owner: ${esc(a.question)}</p></article>`).join("")}</div>` : `<div class="empty-ambiguity">No likely ambiguity was detected by the local wording checks. Review still matters; an empty flag list is not proof that requirements are complete.</div>`;
  return `<div class="section-caption"><h3>Risk-based scenarios</h3><span>${r.coverage}% REQUIREMENT COVERAGE</span></div><div class="table-wrap"><table class="scenario-table"><thead><tr><th>Trace</th><th>Scenario & expected result</th><th>Risk</th><th>Type</th><th>Review</th></tr></thead><tbody>${rows}</tbody></table></div><div class="section-caption section-spaced"><h3>Ambiguity check</h3><span>${r.ambiguities.length} OPEN</span></div>${ambiguity}`;
}
function renderReview(r) {
  const statuses = Object.values(state.reviews); const approved = statuses.filter(x=>x==="approved").length; const changes=statuses.filter(x=>x==="changes").length;
  const rows = r.traceability.map((t) => { const status = state.reviews[t.criterionId] || "pending"; return `<div class="trace-row"><span class="trace-id">${esc(t.criterionId)}</span><div><p>${esc(t.criterion)}</p><small>Mapped to ${t.scenarioIds.map(esc).join(", ") || "no scenario"}</small></div><div class="review-controls"><button type="button" class="review-button ${status==="approved"?"selected":""}" data-review-id="${esc(t.criterionId)}" data-review-status="approved">Reviewed</button><button type="button" class="review-button ${status==="changes"?"selected changes":""}" data-review-id="${esc(t.criterionId)}" data-review-status="changes">Needs changes</button></div></div>`; }).join("");
  return `<div class="notice">Mark each criterion after checking expected behavior and the mapped scenario. Your review choices are saved with this plan on this computer.</div><div class="review-summary"><span>${approved} reviewed</span><span>${changes} needs changes</span><span>${statuses.length-approved-changes} pending</span></div><div class="trace-list">${rows}</div>`;
}
function currentText() {
  if (!state.result) return ""; const r = state.result;
  if (state.tab === "gherkin") return r.gherkin;
  if (state.tab === "cypress") return r.cypress;
  if (state.tab === "review") return r.traceability.map((t)=>`${t.criterionId} [${state.reviews[t.criterionId]}]: ${t.criterion} -> ${t.scenarioIds.join(", ")}`).join("\n");
  return markdown(r);
}
function markdown(r) {
  const lines = [`# QA Scenario Draft: ${r.feature}`, "", `**Product:** ${r.product}  `, `**Target:** ${r.url}  `, `**Generator:** ${r.engine}  `, `**Coverage:** ${r.coverage}%`, "", "## Acceptance criteria & traceability"];
  for (const t of r.traceability) lines.push(`- **${t.criterionId}** — ${t.criterion} → ${t.scenarioIds.join(", ") || "uncovered"}`);
  lines.push("", "## Risk-based scenarios");
  for (const s of r.scenarios) lines.push(`### ${s.id}: ${s.title}`, `- Risk: ${s.risk.level} (${s.risk.score}) — ${s.risk.rationale}`, `- Covers: ${s.acceptanceIds.join(", ")}`, `- Expected: ${s.expectedResult}`, "");
  lines.push("## Ambiguities to clarify");
  if (r.ambiguities.length) for (const a of r.ambiguities) lines.push(`- **${a.criterionId}:** ${a.question}`);
  else lines.push("- No likely ambiguity flagged by local wording checks. Human review still required.");
  lines.push("", "## Gherkin", "```gherkin", r.gherkin.trimEnd(), "```", "", "## Cypress draft", "```javascript", r.cypress.trimEnd(), "```", "", "_Generated draft. Review requirements, selectors, data, and outcomes before use._");
  return lines.join("\n");
}
async function copyOutput() { const value = currentText(); if (!value) return; try { await navigator.clipboard.writeText(value); notify("Copied to clipboard"); } catch { notify("Clipboard access is not available in this browser."); } }
function exportOutput() { if (!state.result) return; const blob = new Blob([markdown(state.result)], {type:"text/markdown;charset=utf-8"}); const url=URL.createObjectURL(blob); const a=document.createElement("a"); a.href=url; a.download="qa-scenario-draft.md"; a.click(); URL.revokeObjectURL(url); notify("Plan and code downloaded"); }
async function showEvaluation() {
  const modal = $("#evaluation-modal"); modal.hidden=false; $("#evaluation-content").innerHTML='<div class="loading-line">Loading checks…</div>';
  try { const response=await fetch("/api/evaluate"); const data=await response.json(); if (!response.ok) throw new Error("Evaluation unavailable");
    const detail=data.details.map((item)=>`<div class="eval-detail"><span>${esc(item.name)}</span><span class="${item.pass?"pass-label":"fail-label"}">${item.pass?"PASS":"REVIEW"} · ${item.coverage}% covered</span></div>`).join("");
    $("#evaluation-content").innerHTML=`<div class="evaluation-cards"><div class="eval-card"><span>SYNTHETIC FIXTURES</span><strong>${data.caseCount}</strong></div><div class="eval-card"><span>CRITERION COVERAGE</span><strong>${data.criterionCoverage}%</strong></div><div class="eval-card"><span>AMBIGUITY RECALL</span><strong>${data.ambiguityRecall}%</strong></div></div><div class="eval-detail-list">${detail}</div><p class="scope-note">${esc(data.scopeNote)} Checks run against local deterministic rules, even when optional AI suggestions are enabled.</p>`;
  } catch (error) { $("#evaluation-content").innerHTML=`<div class="notice error">${esc(error.message)}</div>`; }
}

form.addEventListener("submit", generate);
$("#load-example").addEventListener("click", () => loadExample().catch((error)=>notify(error.message)));
document.querySelectorAll(".tab").forEach((button) => button.addEventListener("click", () => { state.tab=button.dataset.tab; setTab(state.tab); render(); }));
output.addEventListener("click", async (event) => {
  const reviewButton = event.target.closest("[data-review-id]");
  if (reviewButton) {
    state.reviews[reviewButton.dataset.reviewId] = reviewButton.dataset.reviewStatus; render();
    if (state.currentRunId) {
      try {
        const response = await fetch(`/api/runs/${encodeURIComponent(state.currentRunId)}/reviews`, {method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({reviews:state.reviews})});
        const data = await response.json(); if (!response.ok) throw new Error(data.error || "Review could not be saved.");
        await loadHistory();
      } catch (error) { notify(`Review was not saved: ${error.message}`); }
    }
    return;
  }
  const historyButton = event.target.closest("[data-run-id]");
  if (historyButton) loadRun(historyButton.dataset.runId).catch((error)=>notify(error.message));
});
$("#project-select").addEventListener("change", async (event) => {
  state.currentProjectId = event.target.value; localStorage.setItem("scenarioStudioProject", state.currentProjectId);
  clearCurrentResult();
  try { await loadHistory(); } catch (error) { notify(error.message); }
});
$("#show-new-project").addEventListener("click", () => { $("#new-project-form").hidden = !$("#new-project-form").hidden; if (!$("#new-project-form").hidden) $("#new-project-name").focus(); });
$("#create-project").addEventListener("click", () => createProject().catch((error)=>notify(error.message)));
$("#new-project-name").addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); createProject().catch((error)=>notify(error.message)); } });
$("#export-memory").addEventListener("click", () => exportMemory().catch((error)=>notify(error.message)));
$("#import-memory-button").addEventListener("click", () => $("#import-memory-file").click());
$("#import-memory-file").addEventListener("change", (event) => importMemory(event.target.files[0]).catch((error)=>notify(error.message)).finally(() => { event.target.value = ""; }));
$("#copy-output").addEventListener("click", copyOutput); $("#export-output").addEventListener("click", exportOutput);
$("#evaluation-link").addEventListener("click", showEvaluation); $("#close-evaluation").addEventListener("click", () => $("#evaluation-modal").hidden=true);
$("#evaluation-modal").addEventListener("click", (event) => { if (event.target === $("#evaluation-modal")) $("#evaluation-modal").hidden=true; });
document.addEventListener("keydown", (event) => { if (event.key === "Escape") $("#evaluation-modal").hidden=true; });
loadExample().catch(()=>{}); loadProjects().catch((error)=>notify(error.message)); refreshStatus();
