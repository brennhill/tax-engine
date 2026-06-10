const defaultTaxYear = String(new Date().getFullYear() - 1);

const state = {
  year: defaultTaxYear,
  workspace: "",
  csrfToken: "",
  workspaceOpened: false,
  workspaceMode: null,  // "new" | "roll-forward" | null
};

// ---------------------------------------------------------------------------
// Stepper + status badges
//
// The vertical stepper on the left mirrors a per-section workflow state
// (Empty / Incomplete / Saved / Validated / Locked). Status sources are
// per-section: workspace presence, /api/progress completeness for Wave 6
// screens, /api/uploads count for Documents, /api/readiness for the Run
// gate, /api/outputs count for Outputs. After any save we re-poll the
// affected sources and re-render the badges.
// ---------------------------------------------------------------------------

const STEP_STATUS_LABELS = {
  locked: "Locked",
  empty: "Empty",
  incomplete: "Partial",
  saved: "Saved",
  validated: "Ready",
  done: "Done",
  error: "Error",
  current: "Current",
  new: "New",
};

const STEP_LOCK_PARENTS = ["workspace"];  // these never get locked

function setStepStatus(target, status, label) {
  const li = document.querySelector(`.stepper-step[data-nav-target="${target}"]`);
  if (!li) return;
  for (const cls of [
    "is-locked", "is-empty", "is-incomplete", "is-saved",
    "is-validated", "is-done", "is-error", "is-new",
  ]) {
    li.classList.remove(cls);
  }
  li.classList.add(`is-${status}`);
  const badge = li.querySelector(`[data-step-status="${target}"]`);
  if (badge) {
    badge.textContent = label || STEP_STATUS_LABELS[status] || "";
  }
}

function setStepperCurrent(target) {
  for (const li of document.querySelectorAll(".stepper-step")) {
    li.classList.toggle("is-current", li.dataset.navTarget === target);
  }
}

function setStepperLocked(locked) {
  for (const li of document.querySelectorAll(".stepper-step")) {
    const target = li.dataset.navTarget;
    if (STEP_LOCK_PARENTS.includes(target)) continue;
    if (locked) {
      li.classList.add("is-locked");
      const badge = li.querySelector(`[data-step-status="${target}"]`);
      if (badge) badge.textContent = STEP_STATUS_LABELS.locked;
    } else if (li.classList.contains("is-locked")) {
      li.classList.remove("is-locked");
      const badge = li.querySelector(`[data-step-status="${target}"]`);
      if (badge) badge.textContent = STEP_STATUS_LABELS.empty;
      li.classList.add("is-empty");
    }
  }
}

async function refreshStepperStatuses() {
  if (!state.workspaceOpened) {
    setStepperLocked(true);
    setStepStatus("workspace", "new");
    return;
  }
  setStepperLocked(false);
  setStepStatus("workspace", "saved");

  // Per-screen completeness from /api/progress (covers identity,
  // bank_accounts, de_deductions, vorabpauschale, carryovers, children).
  try {
    const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
    const progress = await apiRequest(`/api/progress?${params.toString()}`);
    const byScreen = (progress && progress.completeness && progress.completeness.by_screen) || {};
    for (const screen of Object.keys(byScreen)) {
      const filled = !!byScreen[screen].filled;
      setStepStatus(screen, filled ? "saved" : "empty");
    }
  } catch (_) {
    // ignore — keep prior status
  }

  // Household + Payments: cheap GETs; non-empty taxpayer name / payment marks them saved.
  await refreshHouseholdStatus();
  await refreshPaymentsStatus();
  await refreshPosturesStatus();
  await refreshDocumentsStatus();
  await refreshOutputsStatus();
}

async function refreshHouseholdStatus() {
  try {
    const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
    const payload = await apiRequest(`/api/intake/household?${params.toString()}`);
    const people = (payload && payload.people) || [];
    const filled = people.some((p) => p && String(p.display_name || "").trim());
    setStepStatus("household", filled ? "saved" : "empty");
  } catch (_) {
    setStepStatus("household", "empty");
  }
}

async function refreshPaymentsStatus() {
  try {
    const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
    const payload = await apiRequest(`/api/intake/payments?${params.toString()}`);
    const payments = (payload && payload.payments) || [];
    const filled = payments.some((p) => p && Number(p.amount) > 0);
    setStepStatus("payments", filled ? "saved" : "empty");
  } catch (_) {
    setStepStatus("payments", "empty");
  }
}

async function refreshPosturesStatus() {
  try {
    const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
    const payload = await apiRequest(`/api/postures/state?${params.toString()}`);
    const stateObj = (payload && payload.state) || {};
    const keys = Object.keys(stateObj);
    setStepStatus("postures", keys.length > 0 ? "saved" : "empty");
  } catch (_) {
    setStepStatus("postures", "empty");
  }
}

async function refreshDocumentsStatus() {
  try {
    const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
    const payload = await apiRequest(`/api/uploads?${params.toString()}`);
    const uploads = (payload && payload.uploads) || [];
    setStepStatus("documents", uploads.length > 0 ? "saved" : "empty");
  } catch (_) {
    setStepStatus("documents", "empty");
  }
}

async function refreshOutputsStatus() {
  try {
    const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
    const payload = await apiRequest(`/api/outputs?${params.toString()}`);
    const files = (payload && payload.files) || [];
    setStepStatus("outputs", files.length > 0 ? "done" : "empty");
    setStepStatus("run", files.length > 0 ? "done" : "empty");
  } catch (_) {
    setStepStatus("outputs", "empty");
    setStepStatus("run", "empty");
  }
}

// ---------------------------------------------------------------------------
// First-run quick-start cards
// ---------------------------------------------------------------------------

function bindQuickStartCards() {
  for (const card of document.querySelectorAll(".quick-start-card[data-quick-start]")) {
    card.addEventListener("click", () => handleQuickStart(card.dataset.quickStart));
  }
  const cancel = document.getElementById("workspace-cancel");
  if (cancel) cancel.addEventListener("click", () => showQuickStartCards());
  const switchBtn = document.getElementById("workspace-switch");
  if (switchBtn) switchBtn.addEventListener("click", () => showQuickStartCards());
}

function showQuickStartCards() {
  document.getElementById("quick-start-cards").hidden = false;
  document.getElementById("workspace-form").hidden = true;
  document.getElementById("workspace-active").hidden = true;
  state.workspaceMode = null;
}

function showWorkspaceForm(mode) {
  state.workspaceMode = mode;
  document.getElementById("quick-start-cards").hidden = true;
  document.getElementById("workspace-form").hidden = false;
  document.getElementById("workspace-active").hidden = true;
  const label = document.getElementById("workspace-mode-label");
  if (label) {
    label.textContent =
      mode === "roll-forward"
        ? "Roll forward from a prior year"
        : "Start a new workspace";
  }
  const submit = document.getElementById("workspace-submit");
  if (submit) {
    submit.textContent = mode === "roll-forward" ? "Roll forward" : "Open workspace";
  }
  const sourceField = document.querySelector('[data-workspace-field="source_year"]');
  if (sourceField) sourceField.hidden = mode !== "roll-forward";
}

function showWorkspaceActive(payload) {
  document.getElementById("quick-start-cards").hidden = true;
  document.getElementById("workspace-form").hidden = true;
  const active = document.getElementById("workspace-active");
  active.hidden = false;
  const value = document.getElementById("workspace-active-value");
  if (value) {
    const yearLabel = state.year || "—";
    const pathLabel = (payload && payload.year_root) || state.workspace || "default location";
    value.textContent = `${yearLabel} — ${pathLabel}`;
  }
}

async function handleQuickStart(mode) {
  if (mode === "demo") {
    try {
      const payload = await apiRequest("/api/workspace/demo", {
        method: "POST",
        body: JSON.stringify({ year: "2025" }),
      });
      state.year = "2025";
      state.workspace = "";
      state.workspaceOpened = true;
      renderJson("workspace-output", payload);
      showWorkspaceActive(payload);
      await refreshStepperStatuses();
      await refreshReadiness();
    } catch (error) {
      renderJson("workspace-output", { error: String(error) });
    }
    return;
  }
  if (mode === "new" || mode === "roll-forward") {
    showWorkspaceForm(mode);
  }
}

async function ensureSessionToken() {
  if (state.csrfToken) {
    return state.csrfToken;
  }
  const response = await fetch("/api/session");
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  state.csrfToken = payload.csrf_token;
  return state.csrfToken;
}

async function apiRequest(path, options = {}) {
  const method = String(options.method || "GET").toUpperCase();
  const headers = {
    "Content-Type": "application/json",
    ...(options.headers || {}),
  };
  if (method !== "GET") {
    headers["X-Tax-Intake-CSRF"] = await ensureSessionToken();
  }
  const response = await fetch(path, {
    ...options,
    headers,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.error || `Request failed: ${response.status}`);
  }
  return payload;
}

async function createWorkspace(year, workspace) {
  const payload = await apiRequest("/api/workspace/create", {
    method: "POST",
    body: JSON.stringify({ year, workspace }),
  });
  state.year = year;
  state.workspace = workspace || "";
  state.workspaceOpened = true;
  renderJson("workspace-output", payload);
  showWorkspaceActive(payload);
  await refreshStepperStatuses();
  await refreshReadiness();
  return payload;
}

async function rollForwardWorkspace(sourceYear, year, workspace) {
  const payload = await apiRequest("/api/workspace/roll-forward", {
    method: "POST",
    body: JSON.stringify({ source_year: sourceYear, year, workspace }),
  });
  state.year = year;
  state.workspace = workspace || "";
  state.workspaceOpened = true;
  renderJson("workspace-output", payload);
  showWorkspaceActive(payload);
  await refreshStepperStatuses();
  await refreshReadiness();
  return payload;
}

async function loadWorkspace(year, workspace) {
  const params = new URLSearchParams({ year, workspace });
  const payload = await apiRequest(`/api/workspace?${params.toString()}`);
  state.year = year;
  state.workspace = workspace || "";
  state.workspaceOpened = true;
  renderJson("workspace-output", payload);
  showWorkspaceActive(payload);
  await refreshStepperStatuses();
  await refreshReadiness();
  return payload;
}

async function saveHousehold(payload) {
  const response = await apiRequest("/api/intake/household", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderJson("household-output", response);
  setStepStatus("household", "saved");
  refreshReadiness().catch(() => {});
  return response;
}

async function savePayments(payload) {
  const response = await apiRequest("/api/intake/payments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderJson("payments-output", response);
  setStepStatus("payments", "saved");
  refreshReadiness().catch(() => {});
  return response;
}

async function uploadDocument(payload) {
  const response = await apiRequest("/api/uploads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderJson("documents-output", response);
  setStepStatus("documents", "saved");
  refreshReadiness().catch(() => {});
  return response;
}

async function refreshReadiness() {
  const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
  const payload = await apiRequest(`/api/readiness?${params.toString()}`);
  renderJson("readiness-output", payload);
  return payload;
}

async function refreshOutputs() {
  const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
  const payload = await apiRequest(`/api/outputs?${params.toString()}`);
  renderOutputDownloads(payload);
  renderJson("outputs-output", payload);
  return payload;
}

// H1: streaming-progress run flow.
//
// The wizard kicks off the pipeline via ``/api/run/start`` (returns a
// run_id immediately), then polls ``/api/run/status?run_id=...`` every
// ~500ms to update a progress list of stages with their elapsed time.
// On completion, the wizard auto-navigates to the Outputs screen so
// the user does not have to click anywhere to see the rendered files.

const RUN_POLL_INTERVAL_MS = 500;

async function runPipeline() {
  clearRunFailureCard();
  const startedAt = Date.now();
  const startPayload = await apiRequest("/api/run/start", {
    method: "POST",
    body: JSON.stringify({ year: state.year, workspace: state.workspace }),
  });
  if (!startPayload || !startPayload.run_id) {
    renderJson("run-output", { error: "Server did not return a run_id." });
    return startPayload;
  }
  state.runId = startPayload.run_id;
  renderRunProgressInitial(startPayload.run_id);

  while (true) {
    const params = new URLSearchParams({
      year: state.year,
      workspace: state.workspace,
      run_id: startPayload.run_id,
    });
    const statusPayload = await apiRequest(
      `/api/run/status?${params.toString()}`
    );
    renderRunProgress(statusPayload, startedAt);

    if (statusPayload.status === "completed") {
      if (statusPayload.outputs) {
        renderOutputDownloads(statusPayload.outputs);
        renderJson("outputs-output", statusPayload.outputs);
      }
      // Auto-navigate to Outputs so the user does not have to click
      // through after a successful run.
      showScreen("outputs");
      return statusPayload;
    }
    if (statusPayload.status === "failed") {
      // H2: render a labeled error card with the structured fields the
      // server lifted out of the rule-level error message — stage_id,
      // missing_input_key, authority_url (clickable), original_message.
      renderRunFailureCard(statusPayload.failure || {});
      return statusPayload;
    }
    await new Promise((resolve) => setTimeout(resolve, RUN_POLL_INTERVAL_MS));
  }
}

// H2 also covers the legacy synchronous /api/run path. ``apiRequest``
// raises a generic ``Error`` for any non-200 response, but for a 422
// (StageFailure) we want to surface the structured payload instead of
// the generic ``Request failed: 422`` string. Unwrap such errors via a
// dedicated wrapper that the run-button handler uses.
async function runPipelineWithStructuredError() {
  try {
    return await runPipeline();
  } catch (error) {
    // The streaming flow above never throws — failures land in
    // ``statusPayload.status === "failed"`` and are rendered in the
    // failure card. The catch is a defense-in-depth path for unexpected
    // network / shape errors so the user still gets feedback.
    renderRunFailureCard({
      stage_id: null,
      rule_id: null,
      missing_input_key: null,
      authority_url: null,
      original_message: String(error && error.message ? error.message : error),
    });
    throw error;
  }
}

function clearRunFailureCard() {
  const card = document.getElementById("run-failure-card");
  if (!card) return;
  card.replaceChildren();
  card.classList.remove("is-visible");
}

function renderRunFailureCard(failure) {
  const card = document.getElementById("run-failure-card");
  if (!card) return;
  card.replaceChildren();
  card.classList.add("is-visible");

  const heading = document.createElement("h3");
  heading.textContent = "Pipeline failed";
  card.appendChild(heading);

  const fieldDefs = [
    { key: "stage_id", label: "Stage" },
    { key: "rule_id", label: "Rule" },
    { key: "missing_input_key", label: "Missing input" },
    { key: "authority_url", label: "Statute / authority" },
    { key: "original_message", label: "Message" },
  ];
  const dl = document.createElement("dl");
  dl.className = "run-failure-fields";
  for (const def of fieldDefs) {
    const value = failure ? failure[def.key] : null;
    if (!value) continue;
    const dt = document.createElement("dt");
    dt.textContent = def.label;
    dl.appendChild(dt);
    const dd = document.createElement("dd");
    if (def.key === "authority_url") {
      const link = document.createElement("a");
      link.href = value;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = value;
      dd.appendChild(link);
    } else {
      dd.textContent = value;
    }
    dl.appendChild(dd);
  }
  card.appendChild(dl);
}

function renderRunProgressInitial(runId) {
  const board = document.getElementById("run-output");
  const summary = document.getElementById("run-summary");
  if (!board) return;
  board.replaceChildren();
  if (summary) {
    summary.hidden = false;
    summary.textContent = `Run ${runId} — streaming progress…`;
    summary.className = "run-summary";
  }
}

function renderRunProgress(payload, startedAtMs) {
  const board = document.getElementById("run-output");
  const summary = document.getElementById("run-summary");
  if (!board) return;

  const events = Array.isArray(payload.events) ? payload.events : [];
  // Reduce events to per-stage entries: one row per stage_started, with
  // the stage's status updated when stage_completed arrives. Order
  // follows first-seen order from the event stream so the board grows
  // top-down as the pipeline progresses.
  const byStage = new Map();
  let runFailed = null;
  for (const event of events) {
    if (event.event === "stage_started" && event.stage_id) {
      if (!byStage.has(event.stage_id)) {
        byStage.set(event.stage_id, {
          stage_id: event.stage_id,
          started_elapsed: event.elapsed_seconds || 0,
          completed_elapsed: null,
          phase: event.phase || "",
          state: "running",
        });
      }
    } else if (event.event === "stage_completed" && event.stage_id) {
      const entry = byStage.get(event.stage_id);
      if (entry) {
        entry.completed_elapsed = event.elapsed_seconds || 0;
        entry.state = "complete";
      }
    } else if (event.event === "run_failed") {
      runFailed = event;
      if (event.stage_id && byStage.has(event.stage_id)) {
        byStage.get(event.stage_id).state = "failed";
      } else if (event.stage_id) {
        byStage.set(event.stage_id, {
          stage_id: event.stage_id,
          started_elapsed: event.elapsed_seconds || 0,
          completed_elapsed: event.elapsed_seconds || 0,
          phase: "",
          state: "failed",
        });
      }
    }
  }

  board.replaceChildren();
  const liveElapsedSecs = (Date.now() - startedAtMs) / 1000;
  for (const entry of byStage.values()) {
    const row = document.createElement("div");
    row.className = `run-stage-row is-${entry.state}`;

    const icon = document.createElement("span");
    icon.className = "run-stage-icon";
    icon.setAttribute("aria-hidden", "true");
    icon.textContent = ({ running: "…", complete: "✓", failed: "!" })[entry.state] || "·";
    row.appendChild(icon);

    const label = document.createElement("span");
    label.className = "run-stage-label";
    label.textContent = entry.phase ? `${entry.stage_id} · ${entry.phase}` : entry.stage_id;
    row.appendChild(label);

    const timing = document.createElement("span");
    timing.className = "run-stage-timing";
    if (entry.state === "complete" && entry.completed_elapsed != null) {
      const dt = (entry.completed_elapsed - entry.started_elapsed).toFixed(2);
      timing.textContent = `${dt}s`;
    } else if (entry.state === "failed") {
      timing.textContent = "failed";
    } else {
      const dt = (liveElapsedSecs - entry.started_elapsed).toFixed(1);
      timing.textContent = `${dt}s`;
    }
    row.appendChild(timing);

    if (entry.state === "failed" && runFailed) {
      const failure = document.createElement("div");
      failure.className = "run-stage-failure";
      const pieces = [];
      if (runFailed.rule_id) pieces.push(`Rule: ${runFailed.rule_id}`);
      if (runFailed.missing_input_key) pieces.push(`Missing input: ${runFailed.missing_input_key}`);
      if (runFailed.original_message) pieces.push(runFailed.original_message);
      failure.textContent = pieces.join(" — ");
      if (runFailed.authority_url) {
        failure.append(" · ");
        const link = document.createElement("a");
        link.href = runFailed.authority_url;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        link.textContent = "authority";
        failure.appendChild(link);
      }
      row.appendChild(failure);
    }

    board.appendChild(row);
  }

  if (summary) {
    const stageCount = byStage.size;
    if (payload.status === "running" && payload.current_stage_id) {
      summary.textContent = `Running stage ${payload.current_stage_id} (${stageCount} stages so far, ${liveElapsedSecs.toFixed(1)}s elapsed)`;
      summary.className = "run-summary";
    } else if (payload.status === "completed") {
      const totalElapsed = events.reduce(
        (max, e) => Math.max(max, Number(e.elapsed_seconds) || 0),
        0,
      );
      summary.textContent = `Complete — ${stageCount} stages, ${totalElapsed.toFixed(2)}s total. Opening Outputs.`;
      summary.className = "run-summary is-complete";
    } else if (payload.status === "failed") {
      summary.textContent = `Failed at ${runFailed && runFailed.stage_id ? runFailed.stage_id : "an unknown stage"} after ${liveElapsedSecs.toFixed(1)}s.`;
      summary.className = "run-summary is-failed";
    } else {
      summary.textContent = "Run started — streaming progress…";
      summary.className = "run-summary";
    }
  }
}


function renderJson(targetId, payload) {
  const target = document.getElementById(targetId);
  if (target) {
    target.textContent = JSON.stringify(payload, null, 2);
  }
}

function renderOutputDownloads(payload) {
  const summary = document.getElementById("outputs-summary");
  const list = document.getElementById("outputs-list");
  if (!summary || !list) {
    return;
  }

  summary.replaceChildren();
  list.replaceChildren();

  const outputsRoot = document.createElement("p");
  outputsRoot.textContent = "Generated outputs are under this workspace's outputs/ directory.";
  summary.appendChild(outputsRoot);

  const files = Array.isArray(payload.files) ? payload.files : [];
  if (files.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "No generated output files found yet. Run the pipeline first.";
    list.appendChild(empty);
    return;
  }

  const byCategory = new Map();
  for (const file of files) {
    const category = file.category || "Outputs";
    if (!byCategory.has(category)) {
      byCategory.set(category, []);
    }
    byCategory.get(category).push(file);
  }

  for (const [category, categoryFiles] of byCategory.entries()) {
    const section = document.createElement("section");
    section.className = "output-category";

    const heading = document.createElement("h3");
    heading.textContent = category;
    section.appendChild(heading);

    const items = document.createElement("ul");
    for (const file of categoryFiles) {
      const item = document.createElement("li");
      const link = document.createElement("a");
      const downloadUrl = new URL(file.download_url, window.location.origin);
      if (state.workspace) {
        downloadUrl.searchParams.set("workspace", state.workspace);
      }
      link.href = downloadUrl.toString();
      link.download = file.relative_path ? file.relative_path.split("/").pop() : "";
      link.textContent = file.label || file.relative_path;
      item.appendChild(link);

      // High-value outputs (final-legal-output.json, narratives, verbose
      // report) get a Preview button that opens the in-app preview
      // modal. The server marks eligibility via preview_eligible so the
      // affordance list is centralized in tax_pipeline/intake/outputs.py.
      if (file.preview_eligible) {
        const previewBtn = document.createElement("button");
        previewBtn.type = "button";
        previewBtn.className = "preview-button";
        previewBtn.textContent = "Preview";
        previewBtn.addEventListener("click", () => openOutputPreview(file));
        item.appendChild(previewBtn);
      }

      const path = document.createElement("span");
      path.className = "output-path";
      path.textContent = ` ${file.relative_path}`;
      item.appendChild(path);
      items.appendChild(item);
    }
    section.appendChild(items);
    list.appendChild(section);
  }
}

function showScreen(name) {
  for (const screen of document.querySelectorAll(".screen")) {
    screen.classList.toggle("is-active", screen.dataset.screen === name);
  }
  setStepperCurrent(name);
}

// ---------------------------------------------------------------------------
// Output preview modal (suggestion #5)
// ---------------------------------------------------------------------------

async function openOutputPreview(file) {
  const modal = document.getElementById("output-preview-modal");
  const body = document.getElementById("output-preview-body");
  const title = document.getElementById("output-preview-title");
  if (!modal || !body || !title) return;
  title.textContent = file.label || file.relative_path;
  body.innerHTML = '<p class="rail-empty">Loading preview…</p>';
  modal.hidden = false;
  modal.classList.add("is-open");
  try {
    const params = new URLSearchParams({
      year: state.year,
      workspace: state.workspace,
      path: file.relative_path,
    });
    const payload = await apiRequest(`/api/output-preview?${params.toString()}`);
    renderOutputPreview(body, payload);
  } catch (error) {
    body.innerHTML = `<p class="rail-empty">Preview failed: ${String(error)}</p>`;
  }
}

function closeOutputPreview() {
  const modal = document.getElementById("output-preview-modal");
  if (!modal) return;
  modal.classList.remove("is-open");
  modal.hidden = true;
}

function renderOutputPreview(body, payload) {
  body.replaceChildren();
  if (payload.error) {
    const err = document.createElement("p");
    err.className = "rail-empty";
    err.textContent = payload.error;
    body.appendChild(err);
  }

  if (payload.kind === "json") {
    const highlights = Array.isArray(payload.highlights) ? payload.highlights : [];
    if (highlights.length === 0) {
      const p = document.createElement("p");
      p.className = "rail-empty";
      p.textContent = "No highlight figures recognized in this file.";
      body.appendChild(p);
    } else {
      for (const h of highlights) {
        const row = document.createElement("div");
        row.className = "highlight-row";
        const labelWrap = document.createElement("div");
        const label = document.createElement("strong");
        label.textContent = h.label;
        labelWrap.appendChild(label);
        if (h.detail) {
          const detail = document.createElement("div");
          detail.className = "highlight-detail";
          detail.textContent = h.detail;
          labelWrap.appendChild(detail);
        }
        row.appendChild(labelWrap);
        const amount = document.createElement("span");
        amount.className = "highlight-amount";
        amount.textContent = h.amount;
        row.appendChild(amount);
        body.appendChild(row);
      }
    }
    if (Number(payload.provenance_count) > 0) {
      const prov = document.createElement("p");
      prov.style.marginTop = "1rem";
      prov.style.fontSize = "0.82rem";
      prov.style.color = "var(--ink-faint)";
      prov.textContent = `Audit trail: ${payload.provenance_count} rule-output fingerprints recorded in _provenance.`;
      body.appendChild(prov);
    }
  }

  if (payload.kind === "markdown") {
    const wrap = document.createElement("div");
    wrap.className = "preview-narrative";
    const pre = document.createElement("pre");
    pre.textContent = payload.body_text || "";
    wrap.appendChild(pre);
    body.appendChild(wrap);
  }

  if (payload.kind === "raw") {
    const pre = document.createElement("pre");
    pre.textContent = payload.body_text || "";
    body.appendChild(pre);
  }

  if (payload.truncated) {
    const trunc = document.createElement("p");
    trunc.style.marginTop = "0.75rem";
    trunc.style.fontStyle = "italic";
    trunc.style.color = "var(--ink-faint)";
    trunc.textContent = "Preview truncated. Use Download for the full file.";
    body.appendChild(trunc);
  }
}

function bindOutputPreviewModal() {
  const modal = document.getElementById("output-preview-modal");
  const close = document.getElementById("output-preview-close");
  if (close) close.addEventListener("click", closeOutputPreview);
  if (modal) {
    modal.addEventListener("click", (event) => {
      if (event.target === modal) closeOutputPreview();
    });
  }
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeOutputPreview();
  });
}

function bindNavigation() {
  for (const button of document.querySelectorAll("[data-nav-target]")) {
    button.addEventListener("click", (event) => {
      // Stepper steps may be locked while no workspace is open. Locked
      // steps are not actionable — clicking them just nudges the user
      // back to Workspace so they can pick a starting point.
      if (button.classList && button.classList.contains("is-locked")) {
        event.preventDefault();
        showScreen("workspace");
        return;
      }
      showScreen(button.dataset.navTarget);
    });
  }
}

// ---------------------------------------------------------------------------
// Live readiness side-panel (suggestion #2)
//
// /api/readiness re-runs the workspace validator on every call and is
// cheap (file-presence + lightweight TOML parsing). After each autosave
// save we re-poll, then render the structured groups (missing_config /
// missing_structured / other_errors / sections) into the right-hand
// rail. Errors are clickable buttons that deep-link back to the
// responsible screen via the same data-nav-target convention the
// stepper uses.
// ---------------------------------------------------------------------------

// Maps a readiness error/missing-key string to the screen the user
// would visit to fix it. Falls back to "documents" for anything that
// looks like a raw-input gap, and "workspace" for everything else.
const READINESS_FIELD_HINTS = [
  { pattern: /profile\.json|people\.csv|household|marital/i, target: "household" },
  { pattern: /payments\.csv|prepayment|estimated/i, target: "payments" },
  { pattern: /elections\.csv|posture|treaty/i, target: "postures" },
  { pattern: /identity|tax id|ssn|itin|employer/i, target: "identity" },
  { pattern: /bank|fbar|account/i, target: "bank_accounts" },
  { pattern: /child|kinder|dependent/i, target: "children" },
  { pattern: /carryover|carryforward|ftc/i, target: "carryovers" },
  { pattern: /vorab|invstg|fund/i, target: "vorabpauschale" },
  { pattern: /außergewöhnliche|sonderausgaben|arbeitszimmer|deduction/i, target: "de_deductions" },
  { pattern: /raw|upload|document|lohnsteuer|w-?2|1099/i, target: "documents" },
];

function resolveReadinessTarget(needle) {
  for (const { pattern, target } of READINESS_FIELD_HINTS) {
    if (pattern.test(needle)) return target;
  }
  return "workspace";
}

async function refreshReadiness() {
  const rail = document.getElementById("readiness-rail-body");
  const badge = document.getElementById("readiness-badge");
  const raw = document.getElementById("readiness-output");
  if (!rail) return;
  if (!state.workspaceOpened) {
    rail.innerHTML = '<p class="rail-empty">Open or create a workspace to begin.</p>';
    if (badge) {
      badge.className = "rail-badge";
      badge.textContent = "Not checked";
    }
    return;
  }
  try {
    const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
    const payload = await apiRequest(`/api/readiness?${params.toString()}`);
    renderReadinessRail(payload);
    if (raw) renderJson("readiness-output", payload);
    setStepStatus("run", payload && payload.ready ? "validated" : "incomplete");
  } catch (error) {
    rail.innerHTML = `<p class="rail-empty">Readiness check failed: ${String(error)}</p>`;
    if (badge) {
      badge.className = "rail-badge is-not-ready";
      badge.textContent = "Error";
    }
  }
}

function renderReadinessRail(payload) {
  const rail = document.getElementById("readiness-rail-body");
  const badge = document.getElementById("readiness-badge");
  if (!rail) return;
  rail.replaceChildren();
  if (badge) {
    badge.className = "rail-badge " + (payload && payload.ready ? "is-ready" : "is-not-ready");
    badge.textContent = payload && payload.ready ? "Ready" : "Not ready";
  }

  const groups = (payload && payload.groups) || {};
  const sectionDefs = [
    { key: "missing_config", title: "Missing config" },
    { key: "missing_structured", title: "Missing inputs" },
    { key: "other_errors", title: "Other issues" },
  ];

  let totalIssues = 0;
  for (const def of sectionDefs) {
    const items = Array.isArray(groups[def.key]) ? groups[def.key] : [];
    if (items.length === 0) continue;
    totalIssues += items.length;
    const section = document.createElement("section");
    section.className = "rail-section";

    const title = document.createElement("h3");
    title.className = "rail-section-title";
    const titleLabel = document.createElement("span");
    titleLabel.textContent = def.title;
    title.appendChild(titleLabel);
    const count = document.createElement("span");
    count.className = "rail-section-count";
    count.textContent = String(items.length);
    title.appendChild(count);
    section.appendChild(title);

    const list = document.createElement("ul");
    list.className = "rail-list";
    for (const needle of items) {
      const li = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.className = "rail-item is-error";
      button.textContent = needle;
      const target = resolveReadinessTarget(String(needle));
      button.addEventListener("click", () => showScreen(target));
      li.appendChild(button);
      list.appendChild(li);
    }
    section.appendChild(list);
    rail.appendChild(section);
  }

  if (totalIssues === 0) {
    const ok = document.createElement("p");
    ok.className = "rail-empty";
    ok.textContent = payload && payload.ready
      ? "All required inputs are present. Ready to run."
      : "No structured errors recorded yet.";
    rail.appendChild(ok);
  }
}

function bindWorkspaceForm() {
  const form = document.getElementById("workspace-form");
  if (!form) return;
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const year = String(formData.get("year") || state.year);
    const workspace = String(formData.get("workspace") || "");
    try {
      if (state.workspaceMode === "roll-forward") {
        const sourceYear = String(formData.get("source_year") || "").trim();
        if (!sourceYear) {
          renderJson("workspace-output", {
            error: "Source year is required for roll-forward.",
          });
          return;
        }
        await rollForwardWorkspace(sourceYear, year, workspace);
      } else {
        await createWorkspace(year, workspace);
      }
    } catch (error) {
      renderJson("workspace-output", { error: String(error) });
    }
  });
}

function initializeWorkspaceYearDefault() {
  const workspaceYearInput = document.querySelector("#workspace-form input[name='year']");
  if (workspaceYearInput && !workspaceYearInput.value) {
    workspaceYearInput.value = state.year;
  }
}

function buildHouseholdPayload(form) {
  const formData = new FormData(form);
  const maritalStatus = String(formData.get("marital_status_on_dec_31") || "single");
  const taxpayerName = String(formData.get("taxpayer_name") || "").trim();
  const spouseName = String(formData.get("spouse_name") || "").trim();
  const people = [
    {
      person_id: "person_1",
      display_name: taxpayerName,
      relationship_role: "taxpayer",
      elster_order: "1",
      us_filer: true,
      is_taxpayer: true,
      is_spouse: false,
      citizenship: "US",
      country_of_tax_residence: "DE",
      nra_for_us_return: false,
    },
  ];
  if (maritalStatus === "married") {
    people.push({
      person_id: "person_2",
      display_name: spouseName,
      relationship_role: "spouse",
      elster_order: "2",
      us_filer: false,
      is_taxpayer: false,
      is_spouse: true,
      citizenship: "",
      country_of_tax_residence: "DE",
      nra_for_us_return: true,
    });
  }
  return {
    year: state.year,
    workspace: state.workspace,
    household: {
      marital_status_on_dec_31: maritalStatus,
      germany_filing_posture: String(formData.get("germany_filing_posture") || "single"),
      usa_filing_posture: String(formData.get("usa_filing_posture") || "single"),
    },
    people,
    jurisdictions: {
      germany: { enabled: true },
      usa: {
        enabled: true,
        us_ftc_method: "accrued",
        use_treaty_resourcing: true,
        elect_joint_return_with_nra_spouse: false,
      },
    },
  };
}

function bindHouseholdForm() {
  const form = document.getElementById("household-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveHousehold(buildHouseholdPayload(form));
    } catch (error) {
      renderJson("household-output", { error: String(error) });
    }
  });
}

function buildPaymentsPayload(form) {
  const formData = new FormData(form);
  const payments = [];
  const germanyPrepayment = String(formData.get("germany_prepayment") ?? "").trim();
  const usaEstimatedPayment = String(formData.get("usa_estimated_payment") ?? "").trim();
  if (germanyPrepayment) {
    payments.push(
      {
        jurisdiction: "germany",
        person_id: "",
        payment_type: "income_tax_prepayment",
        amount: germanyPrepayment,
        currency: "EUR",
        source: "intake_wizard",
        note: "Saved through the local intake wizard.",
      },
    );
  }
  if (usaEstimatedPayment) {
    payments.push(
      {
        jurisdiction: "usa",
        person_id: "person_1",
        payment_type: "estimated_tax_payment",
        amount: usaEstimatedPayment,
        currency: "USD",
        source: "intake_wizard",
        note: "Saved through the local intake wizard.",
      },
    );
  }
  return {
    year: state.year,
    workspace: state.workspace,
    payments,
  };
}

function bindPaymentsForm() {
  const form = document.getElementById("payments-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await savePayments(buildPaymentsPayload(form));
    } catch (error) {
      renderJson("payments-output", { error: String(error) });
    }
  });
}

async function fileToBase64(file) {
  const bytes = await file.arrayBuffer();
  let binary = "";
  for (const value of new Uint8Array(bytes)) {
    binary += String.fromCharCode(value);
  }
  return btoa(binary);
}

// ---------------------------------------------------------------------------
// Drag-and-drop batch upload (suggestion #3)
//
// The Documents screen now accepts a batch of files via drag-drop or the
// hidden <input type="file" multiple>. For each dropped file we:
//   1. Pre-classify via /api/uploads/classify-batch (filename-only — no
//      bytes leave the browser at this stage).
//   2. Render a preview row showing the predicted bucket + confidence
//      and an editable bucket override.
//   3. On "Upload all", POST each row's bytes (base64) to /api/uploads
//      with the (possibly overridden) bucket, updating the row state.
//
// The dropzone state lives in module-scoped uploadBatchState; the
// rendered rows are derived from it. File contents stay in-memory until
// the user commits or clears the batch.
// ---------------------------------------------------------------------------

const BUCKET_OVERRIDES = [
  { value: "", label: "Auto (use prediction)" },
  { value: "germany", label: "germany" },
  { value: "us", label: "us" },
  { value: "brokers", label: "brokers" },
  { value: "crypto", label: "crypto" },
  { value: "equity_comp", label: "equity_comp" },
  { value: "receipts", label: "receipts" },
  { value: "real_estate", label: "real_estate" },
];

const uploadBatchState = {
  rows: [],  // { id, file, prediction, override, status, error }
  nextId: 1,
};

function fileBatchId() {
  return `upload-${uploadBatchState.nextId++}`;
}

function bindUploadForm() {
  const form = document.getElementById("document-upload-form");
  if (!form) return;
  // Prevent the legacy submit from triggering a full page reload when a
  // single dropzone-input change happens to bubble a submit.
  form.addEventListener("submit", (event) => event.preventDefault());

  const dropzone = document.getElementById("upload-dropzone");
  const input = document.getElementById("upload-dropzone-input");
  if (dropzone && input) {
    input.addEventListener("change", () => handleUploadFiles(Array.from(input.files || [])));
    dropzone.addEventListener("dragenter", (e) => { e.preventDefault(); dropzone.classList.add("is-dragover"); });
    dropzone.addEventListener("dragover", (e) => { e.preventDefault(); dropzone.classList.add("is-dragover"); });
    dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragover"));
    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.classList.remove("is-dragover");
      const files = Array.from((e.dataTransfer && e.dataTransfer.files) || []);
      if (files.length > 0) {
        handleUploadFiles(files);
      }
    });
  }

  const commitAll = document.getElementById("upload-commit-all");
  if (commitAll) commitAll.addEventListener("click", commitUploadBatch);
  const clearAll = document.getElementById("upload-clear-all");
  if (clearAll) clearAll.addEventListener("click", () => clearUploadBatch());
}

async function handleUploadFiles(files) {
  if (!files || files.length === 0) return;
  const newRows = files.map((file) => ({
    id: fileBatchId(),
    file,
    prediction: null,
    override: "",
    status: "classifying",
    error: null,
  }));
  uploadBatchState.rows.push(...newRows);
  renderUploadBatch();

  try {
    const predictions = await apiRequest("/api/uploads/classify-batch", {
      method: "POST",
      body: JSON.stringify({ filenames: newRows.map((r) => r.file.name) }),
    });
    const predList = (predictions && predictions.predictions) || [];
    for (let i = 0; i < newRows.length; i++) {
      newRows[i].prediction = predList[i] || null;
      newRows[i].status = "ready";
    }
  } catch (error) {
    for (const row of newRows) {
      row.status = "error";
      row.error = String(error);
    }
  }
  renderUploadBatch();
}

function clearUploadBatch() {
  uploadBatchState.rows = [];
  renderUploadBatch();
  const input = document.getElementById("upload-dropzone-input");
  if (input) input.value = "";
}

async function commitUploadBatch() {
  const pending = uploadBatchState.rows.filter((r) => r.status === "ready" || r.status === "error");
  if (pending.length === 0) return;
  const commitBtn = document.getElementById("upload-commit-all");
  if (commitBtn) commitBtn.disabled = true;
  for (const row of pending) {
    row.status = "uploading";
    renderUploadBatch();
    try {
      const content_base64 = await fileToBase64(row.file);
      const response = await uploadDocument({
        year: state.year,
        workspace: state.workspace,
        filename: row.file.name,
        content_base64,
        manual_bucket: row.override || "",
        evidence_only: false,
      });
      row.status = "done";
      row.error = null;
      row.result = response;
    } catch (error) {
      row.status = "error";
      row.error = String(error);
    }
    renderUploadBatch();
  }
  if (commitBtn) commitBtn.disabled = false;
  refreshDocumentsStatus().catch(() => {});
  refreshReadiness().catch(() => {});
}

function renderUploadBatch() {
  const board = document.getElementById("upload-batch");
  const actions = document.getElementById("upload-batch-actions");
  if (!board) return;
  board.replaceChildren();
  if (uploadBatchState.rows.length === 0) {
    board.hidden = true;
    if (actions) actions.hidden = true;
    return;
  }
  board.hidden = false;
  if (actions) actions.hidden = false;

  for (const row of uploadBatchState.rows) {
    const li = document.createElement("div");
    li.className = "upload-row";
    if (row.status === "error") li.classList.add("is-error");
    if (row.status === "uploading" || row.status === "classifying") li.classList.add("is-uploading");
    if (row.status === "done") li.classList.add("is-done");

    const icon = document.createElement("span");
    icon.className = "upload-row-icon";
    icon.textContent = ({
      classifying: "…",
      ready: "↑",
      uploading: "…",
      done: "✓",
      error: "!",
    })[row.status] || "?";
    li.appendChild(icon);

    const meta = document.createElement("div");
    meta.className = "upload-row-meta";
    const name = document.createElement("span");
    name.className = "upload-row-name";
    name.textContent = row.file.name;
    meta.appendChild(name);
    const detail = document.createElement("span");
    detail.className = "upload-row-detail";
    if (row.status === "classifying") {
      detail.textContent = "Classifying…";
    } else if (row.status === "uploading") {
      detail.textContent = "Uploading…";
    } else if (row.status === "done") {
      const r = row.result && row.result.entry ? row.result.entry : row.result;
      const bucket = (r && r.bucket) || (row.prediction && row.prediction.bucket) || "unknown";
      detail.textContent = `Uploaded → ${bucket}`;
    } else if (row.status === "error") {
      detail.textContent = row.error || "Upload failed.";
    } else if (row.prediction) {
      const p = row.prediction;
      const confidence = String(p.confidence || "low");
      const docType = String(p.doc_type || "unknown");
      detail.textContent = `${p.bucket || "unknown"} · ${docType} · ${confidence} confidence`;
      if (confidence === "low") detail.classList.add("is-low-confidence");
    }
    meta.appendChild(detail);
    li.appendChild(meta);

    const select = document.createElement("select");
    select.disabled = row.status === "uploading" || row.status === "done";
    for (const option of BUCKET_OVERRIDES) {
      const opt = document.createElement("option");
      opt.value = option.value;
      opt.textContent = option.label;
      if (option.value === row.override) opt.selected = true;
      select.appendChild(opt);
    }
    select.addEventListener("change", () => {
      row.override = select.value;
    });
    li.appendChild(select);

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "row-action is-danger";
    remove.textContent = row.status === "done" ? "Done" : "Remove";
    remove.disabled = row.status === "done";
    remove.addEventListener("click", () => {
      uploadBatchState.rows = uploadBatchState.rows.filter((r) => r.id !== row.id);
      renderUploadBatch();
    });
    li.appendChild(remove);

    board.appendChild(li);
  }
}

function bindReadinessButton() {
  // The Readiness screen was retired in favour of the live readiness
  // side-panel (see refreshReadiness + the right-rail <aside>). The old
  // ``readiness-button`` may not be in the DOM; guard for that so an
  // older index.html doesn't break the init block.
  const button = document.getElementById("readiness-button");
  if (!button) return;
  button.addEventListener("click", async () => {
    try {
      await refreshReadiness();
    } catch (error) {
      renderJson("readiness-output", { error: String(error) });
    }
  });
}

function bindRunButton() {
  const button = document.getElementById("run-button");
  button.addEventListener("click", async () => {
    try {
      await runPipelineWithStructuredError();
    } catch (_error) {
      // The wrapper already rendered the failure card; swallow the
      // re-raise so the click handler does not propagate to the
      // browser console as an uncaught promise rejection.
    }
  });
}

const POSTURE_SECTION_LABELS = {
  filing_status: "Filing status",
  de_elections: "Germany elections",
  us_elections: "U.S. elections",
  treaty: "Treaty",
  cross_jurisdiction: "Cross-jurisdiction",
  general: "Other",
};

const postureUiState = {
  fields: [],
  values: {},
};

async function fetchPostureRegistry() {
  const payload = await apiRequest("/api/postures");
  postureUiState.fields = Array.isArray(payload.fields) ? payload.fields : [];
  return postureUiState.fields;
}

async function fetchPostureState() {
  const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
  const payload = await apiRequest(`/api/postures/state?${params.toString()}`);
  postureUiState.values = payload.state && typeof payload.state === "object" ? { ...payload.state } : {};
  return postureUiState.values;
}

async function savePostureState() {
  const payload = await apiRequest("/api/postures/state", {
    method: "POST",
    body: JSON.stringify({
      year: state.year,
      workspace: state.workspace,
      state: postureUiState.values,
    }),
  });
  postureUiState.values = payload.state && typeof payload.state === "object" ? { ...payload.state } : {};
  renderJson("postures-output", payload);
  renderPosturesForm();
  return payload;
}

function preconditionsSatisfied(field) {
  if (!Array.isArray(field.requires) || field.requires.length === 0) {
    return { ok: true, missing: [] };
  }
  const missing = [];
  for (const requirement of field.requires) {
    const actual = postureUiState.values[requirement.key];
    if (actual !== requirement.equals) {
      missing.push(requirement);
    }
  }
  return { ok: missing.length === 0, missing };
}

function buildCitationLine(field) {
  const refs = Array.isArray(field.legal_refs) ? field.legal_refs : [];
  const urls = Array.isArray(field.legal_urls) ? field.legal_urls : [];
  if (refs.length === 0) {
    return null;
  }
  const wrapper = document.createElement("span");
  wrapper.className = "posture-field-citations";
  refs.forEach((ref, index) => {
    if (index > 0) {
      wrapper.appendChild(document.createTextNode(" · "));
    }
    const url = urls[index] || urls[0];
    if (url) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = ref;
      wrapper.appendChild(link);
    } else {
      wrapper.appendChild(document.createTextNode(ref));
    }
  });
  return wrapper;
}

function buildInfoMarker(field) {
  const marker = document.createElement("span");
  marker.className = "info-marker";
  marker.textContent = "i";
  marker.tabIndex = 0;
  const refs = Array.isArray(field.legal_refs) ? field.legal_refs.join(" · ") : "";
  const tooltip = field.tooltip + (refs ? `\n\n${refs}` : "");
  marker.setAttribute("data-tooltip", tooltip);
  marker.setAttribute("aria-label", tooltip);
  return marker;
}

function buildPostureControl(field, currentValue, disabled) {
  const wrapper = document.createElement("div");
  wrapper.className = "posture-field-control";

  const onChange = (value) => {
    postureUiState.values[field.key] = value;
    // Update precondition-driven disabled state in-place WITHOUT
    // re-rendering the form (which would steal focus from the active
    // input). Auto-save is scheduled via the form-level event listener
    // attached by attachAutosaveListeners().
    refreshPosturePreconditions();
  };

  if (field.widget === "radio") {
    for (const option of field.options || []) {
      const id = `posture-${field.key}-${option.value}`.replace(/[^A-Za-z0-9_-]/g, "_");
      const label = document.createElement("label");
      label.htmlFor = id;
      const input = document.createElement("input");
      input.type = "radio";
      input.id = id;
      input.name = `posture::${field.key}`;
      input.value = option.value;
      input.checked = String(currentValue ?? "") === String(option.value);
      input.disabled = disabled;
      input.addEventListener("change", () => onChange(option.value));
      label.appendChild(input);
      label.appendChild(document.createTextNode(` ${option.label}`));
      wrapper.appendChild(label);
    }
  } else if (field.widget === "select") {
    const select = document.createElement("select");
    select.disabled = disabled;
    select.name = `posture::${field.key}`;
    for (const option of field.options || []) {
      const optionEl = document.createElement("option");
      optionEl.value = option.value;
      optionEl.textContent = option.label;
      if (String(currentValue ?? "") === String(option.value)) {
        optionEl.selected = true;
      }
      select.appendChild(optionEl);
    }
    select.addEventListener("change", () => onChange(select.value));
    wrapper.appendChild(select);
  } else if (field.widget === "checkbox") {
    const label = document.createElement("label");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.checked = currentValue === true || currentValue === "true" || currentValue === 1 || currentValue === "1";
    input.disabled = disabled;
    input.addEventListener("change", () => onChange(input.checked));
    label.appendChild(input);
    label.appendChild(document.createTextNode(" Enabled"));
    wrapper.appendChild(label);
  } else if (field.widget === "number") {
    const input = document.createElement("input");
    input.type = "number";
    input.value = currentValue ?? "";
    input.disabled = disabled;
    input.addEventListener("input", () => onChange(input.value));
    wrapper.appendChild(input);
  } else {
    const input = document.createElement("input");
    input.type = "text";
    input.value = currentValue ?? "";
    input.disabled = disabled;
    input.addEventListener("input", () => onChange(input.value));
    wrapper.appendChild(input);
  }

  return wrapper;
}

function renderPosturesForm() {
  const root = document.getElementById("postures-sections");
  if (!root) {
    return;
  }
  root.replaceChildren();

  const grouped = new Map();
  for (const field of postureUiState.fields) {
    const section = field.section || "general";
    if (!grouped.has(section)) {
      grouped.set(section, []);
    }
    grouped.get(section).push(field);
  }

  for (const [section, fields] of grouped.entries()) {
    const sectionEl = document.createElement("section");
    sectionEl.className = "postures-section";
    sectionEl.dataset.section = section;

    const heading = document.createElement("h3");
    heading.textContent = POSTURE_SECTION_LABELS[section] || section;
    sectionEl.appendChild(heading);

    for (const field of fields) {
      const precondition = preconditionsSatisfied(field);
      const disabled = !field.engine_supported || !precondition.ok;
      const fieldEl = document.createElement("div");
      fieldEl.className = "posture-field";
      fieldEl.dataset.postureKey = field.key;
      if (disabled) {
        fieldEl.classList.add("is-disabled");
      }

      const header = document.createElement("div");
      header.className = "posture-field-header";

      const labelText = document.createElement("span");
      labelText.className = "posture-field-label";
      labelText.textContent = field.label;
      header.appendChild(labelText);

      header.appendChild(buildInfoMarker(field));

      const citation = buildCitationLine(field);
      if (citation) {
        header.appendChild(citation);
      }

      if (!field.engine_supported) {
        const marker = document.createElement("span");
        marker.className = "coming-soon-marker";
        marker.textContent = field.coming_soon_wave ? `coming soon · ${field.coming_soon_wave}` : "coming soon";
        header.appendChild(marker);
      }

      fieldEl.appendChild(header);

      if (!precondition.ok) {
        const banner = document.createElement("div");
        banner.className = "posture-precondition-banner";
        const requirementSummary = precondition.missing
          .map((req) => `${req.key}=${JSON.stringify(req.equals)}`)
          .join(", ");
        banner.textContent = `Requires ${requirementSummary} before this field can be edited.`;
        fieldEl.appendChild(banner);
      }

      const currentValue = postureUiState.values[field.key];
      fieldEl.appendChild(buildPostureControl(field, currentValue, disabled));
      sectionEl.appendChild(fieldEl);
    }
    root.appendChild(sectionEl);
  }
}

function refreshPosturePreconditions() {
  // Update only the disabled-state of each posture field in place. This
  // is called on every onChange so dependent fields lock/unlock without
  // re-rendering the whole form (which would lose focus on the active
  // input).
  for (const field of postureUiState.fields) {
    const fieldEl = document.querySelector(`.posture-field[data-posture-key='${field.key}']`);
    if (!fieldEl) continue;
    const precondition = preconditionsSatisfied(field);
    const disabled = !field.engine_supported || !precondition.ok;
    fieldEl.classList.toggle("is-disabled", disabled);
    for (const input of fieldEl.querySelectorAll("input, select")) {
      input.disabled = disabled;
    }
  }
}

async function loadPosturesScreen() {
  const validation = document.getElementById("postures-validation");
  if (validation) {
    validation.textContent = "";
  }
  try {
    await fetchPostureRegistry();
    await fetchPostureState();
    renderPosturesForm();
  } catch (error) {
    if (validation) {
      validation.textContent = String(error);
    }
  }
}

async function savePostureStateAutoSave() {
  // Auto-save variant: posts current values, but does NOT call
  // renderPosturesForm() on success (that would steal focus). The
  // server response replaces postureUiState.values, but the DOM
  // already reflects the user's intent, so we skip the re-render and
  // only refresh the precondition gating (server may have normalized
  // values).
  const payload = await apiRequest("/api/postures/state", {
    method: "POST",
    body: JSON.stringify({
      year: state.year,
      workspace: state.workspace,
      state: postureUiState.values,
    }),
  });
  postureUiState.values =
    payload.state && typeof payload.state === "object" ? { ...payload.state } : {};
  renderJson("postures-output", payload);
  refreshPosturePreconditions();
  return payload;
}

function bindPosturesScreen() {
  const form = document.getElementById("postures-form");
  if (!form) {
    return;
  }

  registerScreenSaver("postures", savePostureStateAutoSave);
  attachAutosaveListeners(form, "postures");

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const validation = document.getElementById("postures-validation");
    if (validation) validation.textContent = "";
    autosaveSaveNow("postures");
  });

  for (const button of document.querySelectorAll("[data-nav-target='postures']")) {
    button.addEventListener("click", () => {
      loadPosturesScreen();
    });
  }
}

function bindOutputsButton() {
  const button = document.getElementById("outputs-button");
  button.addEventListener("click", async () => {
    try {
      await refreshOutputs();
    } catch (error) {
      renderJson("outputs-output", { error: String(error) });
    }
  });
}

// ---------------------------------------------------------------------------
// Auto-save controller — debounced, per-screen, with status pill + global
// indicator, exponential-backoff retries, and beforeunload warning.
// ---------------------------------------------------------------------------

const AUTOSAVE_DEBOUNCE_MS = 800;
const AUTOSAVE_BACKOFF_SCHEDULE_MS = [1000, 2000, 4000, 8000, 16000, 30000];
const AUTOSAVE_MAX_RETRIES = 3;

const autosaveControllers = new Map();

function getAutosaveController(screen) {
  let controller = autosaveControllers.get(screen);
  if (!controller) {
    controller = {
      screen,
      timer: null,
      inFlight: null,        // Promise of the current POST, or null.
      queued: false,         // True if an edit arrived while inFlight.
      retryCount: 0,
      retryTimer: null,
      lastError: null,
      lastSavedAt: null,
      hasUnsavedChanges: false,
      // Saver: () => Promise<response>. Set once per screen.
      saver: null,
    };
    autosaveControllers.set(screen, controller);
  }
  return controller;
}

function setScreenStatus(screen, kind, label) {
  const target = document.querySelector(`[data-screen-status='${screen}']`);
  if (!target) return;
  target.classList.remove("is-saving", "is-saved", "is-retrying", "is-error");
  if (kind) target.classList.add(kind);
  target.textContent = label;
  refreshGlobalStatus();
  // Mirror the per-screen save status onto the left-rail stepper badge
  // so the user sees progress in one glance without scrolling the form.
  // The stepper also re-polls /api/readiness opportunistically — a save
  // that drives readiness from "Not ready" to "Ready" is what should
  // unlock the Run step.
  if (kind === "is-saved") {
    setStepStatus(screen, "saved");
    refreshReadiness().catch(() => {});
  }
}

function refreshGlobalStatus() {
  const target = document.getElementById("autosave-global-status");
  if (!target) return;
  let unsavedScreens = 0;
  let errorScreens = 0;
  for (const controller of autosaveControllers.values()) {
    if (controller.lastError) errorScreens += 1;
    if (controller.hasUnsavedChanges || controller.inFlight) unsavedScreens += 1;
  }
  target.classList.remove("is-pending", "is-error");
  if (errorScreens > 0) {
    target.classList.add("is-error");
    target.textContent = `${errorScreens} screen${errorScreens === 1 ? "" : "s"} error`;
  } else if (unsavedScreens > 0) {
    target.classList.add("is-pending");
    target.textContent = `${unsavedScreens} screen${unsavedScreens === 1 ? "" : "s"} have unsaved changes`;
  } else {
    target.textContent = "All saved";
  }
}

function showAutosaveBanner(show) {
  const banner = document.getElementById("autosave-banner");
  if (!banner) return;
  banner.hidden = !show;
}

function formatSavedAt(date) {
  const pad = (n) => String(n).padStart(2, "0");
  return `Saved ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`;
}

function autosaveSchedule(screen, opts = {}) {
  const controller = getAutosaveController(screen);
  if (!controller.saver) return;
  controller.hasUnsavedChanges = true;
  if (controller.lastError && !opts.clearError) {
    // Don't keep auto-retrying once we've seen a 400 — wait for the user
    // to edit and retrigger. The new edit clears the error implicitly.
  }
  // Clear the validation error display when the user resumes editing.
  controller.lastError = null;
  setScreenStatus(screen, null, "Unsaved");
  if (controller.timer) {
    clearTimeout(controller.timer);
  }
  const delay = opts.immediate ? 0 : AUTOSAVE_DEBOUNCE_MS;
  controller.timer = setTimeout(() => {
    controller.timer = null;
    autosaveFire(screen);
  }, delay);
}

function autosaveFire(screen) {
  const controller = getAutosaveController(screen);
  if (!controller.saver) return;
  if (controller.inFlight) {
    controller.queued = true;
    return;
  }
  setScreenStatus(screen, "is-saving", "Saving…");
  controller.inFlight = controller.saver()
    .then((response) => {
      controller.retryCount = 0;
      controller.lastError = null;
      controller.lastSavedAt = new Date();
      controller.hasUnsavedChanges = false;
      showAutosaveBanner(false);
      setScreenStatus(screen, "is-saved", formatSavedAt(controller.lastSavedAt));
      // Clear inline field-error markers on success.
      clearFieldErrorMarkers(screen);
      return response;
    })
    .catch((error) => {
      const message = String(error && error.message ? error.message : error);
      // Distinguish 400 (validation, do NOT retry) from 5xx/network (retry).
      const isValidation = /Request failed: 4\d\d/.test(message) || /^4\d\d:/.test(message);
      if (isValidation) {
        controller.lastError = message;
        controller.hasUnsavedChanges = true;
        setScreenStatus(screen, "is-error", `Error: ${message}`);
        showFieldErrorInline(screen, message);
      } else {
        controller.retryCount += 1;
        if (controller.retryCount > AUTOSAVE_MAX_RETRIES) {
          showAutosaveBanner(true);
        }
        const delay = AUTOSAVE_BACKOFF_SCHEDULE_MS[
          Math.min(controller.retryCount - 1, AUTOSAVE_BACKOFF_SCHEDULE_MS.length - 1)
        ];
        setScreenStatus(screen, "is-retrying", `Unsaved — retrying in ${Math.round(delay / 1000)}s…`);
        if (controller.retryTimer) clearTimeout(controller.retryTimer);
        controller.retryTimer = setTimeout(() => {
          controller.retryTimer = null;
          autosaveFire(screen);
        }, delay);
      }
    })
    .finally(() => {
      controller.inFlight = null;
      if (controller.queued && !controller.lastError) {
        controller.queued = false;
        // Re-enter debounce so further edits can coalesce.
        autosaveSchedule(screen);
      } else {
        controller.queued = false;
      }
    });
}

function clearFieldErrorMarkers(screen) {
  const root = document.querySelector(`[data-screen='${screen}']`);
  if (!root) return;
  for (const el of root.querySelectorAll(".screen-field-error")) {
    el.remove();
  }
  for (const el of root.querySelectorAll(".screen-field.has-error")) {
    el.classList.remove("has-error");
  }
}

function showFieldErrorInline(screen, message) {
  // Best effort: the backend ScreenValidationError messages mention the
  // field key (e.g., "us_ssn_or_itin must be 9 digits"). We try to find a
  // matching [data-field-key] and attach the error there. Otherwise we
  // surface in the screen-validation div.
  const root = document.querySelector(`[data-screen='${screen}']`);
  if (!root) return;
  clearFieldErrorMarkers(screen);
  const validation = document.querySelector(`[data-screen-validation='${screen}']`);
  if (validation) validation.textContent = message;
  // Try to find a referenced field key in the message and highlight it.
  for (const el of root.querySelectorAll("[data-field-key]")) {
    const key = el.dataset.fieldKey;
    if (key && message.includes(key)) {
      el.classList.add("has-error");
      const err = document.createElement("div");
      err.className = "screen-field-error";
      err.textContent = message;
      el.appendChild(err);
      break;
    }
  }
}

function registerScreenSaver(screen, saver) {
  const controller = getAutosaveController(screen);
  controller.saver = saver;
}

function autosaveSaveNow(screen) {
  const controller = getAutosaveController(screen);
  if (!controller.saver) return;
  if (controller.timer) {
    clearTimeout(controller.timer);
    controller.timer = null;
  }
  autosaveFire(screen);
}

function attachAutosaveListeners(rootEl, screen, opts = {}) {
  if (!rootEl || rootEl.dataset.autosaveBound === "1") return;
  rootEl.dataset.autosaveBound = "1";
  const onChange = (event) => {
    const target = event.target;
    if (!target || !target.tagName) return;
    const tag = target.tagName.toUpperCase();
    if (tag !== "INPUT" && tag !== "SELECT" && tag !== "TEXTAREA") return;
    // Checkboxes / radios / select dropdowns save immediately on change
    // (single-click intent). Free-text and number inputs use the debounce.
    if (target.type === "checkbox" || target.type === "radio" || tag === "SELECT") {
      if (event.type === "change") {
        autosaveSchedule(screen, { immediate: true });
      }
      return;
    }
    if (event.type === "input" || event.type === "change" || event.type === "blur") {
      autosaveSchedule(screen);
    }
  };
  rootEl.addEventListener("input", onChange);
  rootEl.addEventListener("change", onChange);
  rootEl.addEventListener("blur", onChange, true);
}

window.addEventListener("beforeunload", (event) => {
  for (const controller of autosaveControllers.values()) {
    if (controller.hasUnsavedChanges || controller.timer || controller.inFlight) {
      event.preventDefault();
      event.returnValue = "";
      return "";
    }
  }
  return undefined;
});

// ---------------------------------------------------------------------------
// Wave 6 — partial-save / restore screens
// ---------------------------------------------------------------------------

const SCREEN_NAMES = ["identity", "bank_accounts", "de_deductions", "vorabpauschale", "carryovers", "children"];

const SCREEN_CONFIG = {
  identity: {
    kind: "person_blocks",
    person_roles: [
      { key: "taxpayer", label: "Taxpayer" },
      { key: "spouse", label: "Spouse" },
    ],
    fields: [
      { key: "full_legal_name", label: "Full legal name", widget: "text" },
      { key: "address_street", label: "Street address", widget: "text" },
      { key: "address_city", label: "City", widget: "text" },
      { key: "address_postal_code", label: "Postal code", widget: "text" },
      { key: "address_country", label: "Country (ISO-3166 alpha-2)", widget: "text", placeholder: "DE" },
      { key: "us_ssn_or_itin", label: "U.S. SSN or ITIN", widget: "text", placeholder: "9 digits" },
      { key: "german_tax_id", label: "German Steuer-ID", widget: "text", placeholder: "11 digits" },
      { key: "date_of_birth", label: "Date of birth", widget: "date" },
      {
        key: "citizenship_status",
        label: "Citizenship / status",
        widget: "select",
        options: [
          { value: "", label: "—" },
          { value: "us_citizen", label: "U.S. citizen" },
          { value: "us_green_card", label: "U.S. green-card holder" },
          { value: "neither", label: "Neither" },
        ],
      },
      { key: "employment_city", label: "Employment city", widget: "text" },
      { key: "employment_country", label: "Employment country (ISO alpha-2)", widget: "text", placeholder: "DE" },
    ],
  },
  bank_accounts: {
    kind: "rows",
    list_key: "accounts",
    columns: [
      { key: "label", label: "Label", widget: "text" },
      { key: "country", label: "Country", widget: "text", placeholder: "DE" },
      { key: "account_number", label: "Account / IBAN", widget: "text" },
      { key: "year_end_balance_usd", label: "Year-end balance (USD)", widget: "number" },
      { key: "linked_certificate_hash", label: "Cert. SHA-256", widget: "text" },
    ],
  },
  de_deductions: {
    kind: "fields",
    fields: [
      { key: "medical_expenses_eur", label: "Medical expenses (EUR)", widget: "number" },
      { key: "charitable_donations_eur", label: "Charitable donations (EUR)", widget: "number" },
      { key: "support_payments_eur", label: "Support payments (EUR)", widget: "number" },
      {
        key: "support_recipient_relationship",
        label: "Support recipient relationship",
        widget: "select",
        options: [
          { value: "", label: "—" },
          { value: "estranged_spouse", label: "Estranged spouse" },
          { value: "divorced_spouse", label: "Divorced spouse" },
          { value: "parent", label: "Parent" },
          { value: "child_no_kindergeld", label: "Child (no Kindergeld)" },
        ],
      },
      { key: "support_recipient_income_eur", label: "Recipient's own income (EUR)", widget: "number" },
      { key: "gdb", label: "Grad der Behinderung (GdB)", widget: "number", placeholder: "0, 20, 30 ... 100" },
      { key: "hilflos_or_blind", label: "Hilflos or blind?", widget: "checkbox" },
      { key: "arbeitszimmer_claimed", label: "Claim Arbeitszimmer (§ 4 (5) 1 Nr. 6b)?", widget: "checkbox" },
      { key: "arbeitszimmer_qualifies_as_mittelpunkt", label: "Home office is Mittelpunkt?", widget: "checkbox" },
      { key: "arbeitszimmer_actual_costs_eur", label: "Arbeitszimmer actual costs (EUR)", widget: "number" },
      { key: "taxpayer_birth_year", label: "Taxpayer birth year", widget: "number", placeholder: "YYYY" },
    ],
  },
  vorabpauschale: {
    kind: "rows",
    list_key: "funds",
    columns: [
      { key: "symbol", label: "Symbol / ISIN", widget: "text" },
      { key: "fund_name", label: "Fund name", widget: "text" },
      { key: "nav_start_eur", label: "NAV start (EUR)", widget: "number" },
      { key: "nav_end_eur", label: "NAV end (EUR)", widget: "number" },
      { key: "ausschuettung_eur", label: "Distributions (EUR)", widget: "number" },
      { key: "months_held", label: "Months held (0-12)", widget: "number" },
      {
        key: "fund_classification",
        label: "Fund class",
        widget: "select",
        options: [
          { value: "", label: "—" },
          { value: "aktienfonds", label: "Aktienfonds" },
          { value: "mischfonds", label: "Mischfonds" },
          { value: "immobilien_deutsch", label: "Immobilienfonds (DE)" },
          { value: "immobilien_auslaendisch", label: "Immobilienfonds (foreign)" },
          { value: "sonstige", label: "Sonstige" },
        ],
      },
    ],
  },
  carryovers: {
    kind: "fields",
    fields: [
      { key: "us_passive_ftc_carryover_2024_usd", label: "US FTC carryover 2024 — passive (USD)", widget: "number" },
      { key: "us_general_ftc_carryover_2024_usd", label: "US FTC carryover 2024 — general (USD)", widget: "number" },
      { key: "us_short_term_capital_loss_carryover_2024_usd", label: "US short-term cap loss carry 2024 (USD)", widget: "number" },
      { key: "us_long_term_capital_loss_carryover_2024_usd", label: "US long-term cap loss carry 2024 (USD)", widget: "number" },
      { key: "de_stock_loss_carryforward_2024_eur", label: "DE Aktienverlust 2024 (EUR)", widget: "number" },
      { key: "de_non_stock_loss_carryforward_2024_eur", label: "DE non-stock loss 2024 (EUR)", widget: "number" },
    ],
  },
  children: {
    // One row per child. Backend (screens.py:write_children_state) auto-
    // assigns ``child_id`` for new rows, so the editor exposes the human-
    // facing fields only. The CSV columns map to 26 U.S.C. § 24 / § 152
    // (CTC / ODC) and § 31, § 32 EStG (Kinderfreibetrag / Kindergeld
    // Günstigerprüfung).
    kind: "rows",
    list_key: "children",
    columns: [
      { key: "name", label: "Full legal name", widget: "text" },
      { key: "date_of_birth", label: "Date of birth", widget: "date" },
      { key: "ssn", label: "U.S. SSN", widget: "text", placeholder: "9 digits" },
      { key: "itin", label: "U.S. ITIN", widget: "text", placeholder: "9 digits" },
      { key: "steuer_id", label: "German Steuer-ID", widget: "text", placeholder: "11 digits" },
      {
        key: "relationship",
        label: "Relationship",
        widget: "select",
        options: [
          { value: "", label: "—" },
          { value: "qualifying_child", label: "Qualifying child" },
          { value: "qualifying_relative", label: "Qualifying relative" },
        ],
      },
      { key: "months_in_household", label: "Months in DE household (0-12)", widget: "number" },
      { key: "months_in_us_household", label: "Months in U.S. household (0-12)", widget: "number" },
      { key: "annual_gross_income_eur", label: "Child's gross income (EUR)", widget: "number" },
      { key: "annual_gross_income_usd", label: "Child's gross income (USD)", widget: "number" },
      { key: "kindergeld_received_eur", label: "Kindergeld received (EUR)", widget: "number" },
      {
        key: "kindergeld_recipient",
        label: "Kindergeld recipient",
        widget: "select",
        options: [
          { value: "", label: "—" },
          { value: "taxpayer", label: "Taxpayer" },
          { value: "spouse", label: "Spouse" },
          { value: "other_parent", label: "Other parent" },
          { value: "none", label: "None" },
        ],
      },
      { key: "disability_gdb", label: "Disability GdB (0-100)", widget: "number" },
    ],
  },
};

const screenUiState = {
  metadata: {},
  values: {},        // {screen: state-shape}
  loaded: {},        // {screen: bool}
  progress: null,
};

async function fetchScreenMetadata() {
  if (screenUiState.metadata && Object.keys(screenUiState.metadata).length > 0) {
    return screenUiState.metadata;
  }
  const payload = await apiRequest("/api/screens/metadata");
  screenUiState.metadata = payload.screens || {};
  return screenUiState.metadata;
}

async function fetchScreenState(screen) {
  const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
  const payload = await apiRequest(`/api/${screen}/state?${params.toString()}`);
  screenUiState.values[screen] = payload.state || {};
  screenUiState.loaded[screen] = true;
  return screenUiState.values[screen];
}

async function postScreenState(screen, body) {
  const payload = await apiRequest(`/api/${screen}/state`, {
    method: "POST",
    body: JSON.stringify({
      year: state.year,
      workspace: state.workspace,
      state: body,
    }),
  });
  screenUiState.values[screen] = payload.state || {};
  return payload;
}

async function fetchProgress() {
  if (!state.workspace && !state.year) {
    return null;
  }
  try {
    const params = new URLSearchParams({ year: state.year, workspace: state.workspace });
    const payload = await apiRequest(`/api/progress?${params.toString()}`);
    screenUiState.progress = payload;
    renderProgressSummary();
    return payload;
  } catch (_error) {
    return null;
  }
}

function renderProgressSummary() {
  const target = document.getElementById("progress-summary");
  if (!target) {
    return;
  }
  const completeness = (screenUiState.progress && screenUiState.progress.completeness) || null;
  if (!completeness) {
    target.textContent = "Progress: – of – sections filled";
    return;
  }
  target.textContent = `Progress: ${completeness.filled} of ${completeness.total} sections filled`;
}

function fieldMetadata(screen, fieldKey) {
  const screenMeta = screenUiState.metadata[screen] || {};
  return screenMeta[fieldKey] || null;
}

function buildScreenInfoMarker(screen, fieldKey) {
  const meta = fieldMetadata(screen, fieldKey);
  if (!meta) {
    return null;
  }
  const marker = document.createElement("span");
  marker.className = "info-marker";
  marker.textContent = "i";
  marker.tabIndex = 0;
  const refs = Array.isArray(meta.legal_refs) ? meta.legal_refs.join(" · ") : "";
  const tooltip = (meta.tooltip || "") + (refs ? `\n\n${refs}` : "");
  marker.setAttribute("data-tooltip", tooltip);
  marker.setAttribute("aria-label", tooltip);
  return marker;
}

function buildScreenCitation(screen, fieldKey) {
  const meta = fieldMetadata(screen, fieldKey);
  if (!meta) {
    return null;
  }
  const refs = Array.isArray(meta.legal_refs) ? meta.legal_refs : [];
  const urls = Array.isArray(meta.legal_urls) ? meta.legal_urls : [];
  if (refs.length === 0) {
    return null;
  }
  const wrapper = document.createElement("span");
  wrapper.className = "posture-field-citations";
  refs.forEach((ref, index) => {
    if (index > 0) {
      wrapper.appendChild(document.createTextNode(" · "));
    }
    const url = urls[index] || urls[0];
    if (url) {
      const link = document.createElement("a");
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = ref;
      wrapper.appendChild(link);
    } else {
      wrapper.appendChild(document.createTextNode(ref));
    }
  });
  return wrapper;
}

function buildScreenInput(field, currentValue, onChange) {
  let input;
  if (field.widget === "select") {
    input = document.createElement("select");
    for (const option of field.options || []) {
      const optionEl = document.createElement("option");
      optionEl.value = option.value;
      optionEl.textContent = option.label;
      if (String(currentValue ?? "") === String(option.value)) {
        optionEl.selected = true;
      }
      input.appendChild(optionEl);
    }
    input.addEventListener("change", () => onChange(input.value));
  } else if (field.widget === "checkbox") {
    input = document.createElement("input");
    input.type = "checkbox";
    input.checked = currentValue === true || currentValue === "true" || currentValue === 1 || currentValue === "1";
    input.addEventListener("change", () => onChange(input.checked));
  } else if (field.widget === "number") {
    input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.value = currentValue ?? "";
    if (field.placeholder) input.placeholder = field.placeholder;
    input.addEventListener("input", () => onChange(input.value));
  } else if (field.widget === "date") {
    input = document.createElement("input");
    input.type = "date";
    input.value = currentValue ?? "";
    input.addEventListener("input", () => onChange(input.value));
  } else {
    input = document.createElement("input");
    input.type = "text";
    input.value = currentValue ?? "";
    if (field.placeholder) input.placeholder = field.placeholder;
    input.addEventListener("input", () => onChange(input.value));
  }
  return input;
}

function fieldCurrency(screen, fieldKey) {
  // Currency comes from the screen metadata published by the backend.
  // Money fields ending in _eur or _usd carry "EUR" or "USD"; all others
  // carry "" so we can skip the marker without a special-case.
  const meta = fieldMetadata(screen, fieldKey);
  return meta && meta.currency ? meta.currency : "";
}

function buildFieldRow(screen, field, currentValue, onChange) {
  const fieldEl = document.createElement("div");
  fieldEl.className = "screen-field";
  fieldEl.dataset.fieldKey = field.key;

  const header = document.createElement("div");
  header.className = "screen-field-header";

  const labelText = document.createElement("span");
  labelText.className = "screen-field-label";
  labelText.textContent = field.label;
  header.appendChild(labelText);

  // Render a currency tag (EUR / USD) right after the label so the user
  // never has to guess which currency the field expects. The tag is
  // visible alongside any (EUR) / (USD) suffix already in the label,
  // which is intentional redundancy: belt + suspenders.
  const currency = fieldCurrency(screen, field.key);
  if (currency) {
    const tag = document.createElement("span");
    tag.className = "currency-tag";
    tag.textContent = currency;
    header.appendChild(tag);
  }

  const marker = buildScreenInfoMarker(screen, field.key);
  if (marker) header.appendChild(marker);
  const citation = buildScreenCitation(screen, field.key);
  if (citation) header.appendChild(citation);

  fieldEl.appendChild(header);

  const control = document.createElement("div");
  control.className = "screen-field-control";
  if (currency && field.widget === "number") {
    // Wrap the number input with a currency-prefix glyph and a trailing
    // pill so the active input always carries its currency in two
    // places at once. The user never has to scan for the unit.
    const wrap = document.createElement("span");
    wrap.className = "input-with-currency";
    const prefix = document.createElement("span");
    prefix.className = "currency-prefix";
    prefix.textContent = currency === "USD" ? "$" : (currency === "EUR" ? "€" : "");
    wrap.appendChild(prefix);
    wrap.appendChild(buildScreenInput(field, currentValue, onChange));
    const pill = document.createElement("span");
    pill.className = "currency";
    pill.textContent = currency;
    wrap.appendChild(pill);
    control.appendChild(wrap);
  } else {
    control.appendChild(buildScreenInput(field, currentValue, onChange));
  }
  fieldEl.appendChild(control);

  return fieldEl;
}

function renderIdentityScreen(values) {
  const root = document.querySelector("[data-screen-sections='identity']");
  if (!root) return;
  root.replaceChildren();
  const config = SCREEN_CONFIG.identity;

  if (!values.taxpayer) values.taxpayer = {};
  if (!values.spouse) values.spouse = {};

  for (const role of config.person_roles) {
    const sectionEl = document.createElement("section");
    sectionEl.className = "screen-section";
    sectionEl.dataset.role = role.key;
    const heading = document.createElement("h3");
    heading.textContent = role.label;
    sectionEl.appendChild(heading);

    if (!values[role.key]) values[role.key] = {};

    for (const field of config.fields) {
      const current = values[role.key][field.key];
      const onChange = (val) => {
        values[role.key][field.key] = val;
      };
      sectionEl.appendChild(buildFieldRow("identity", field, current, onChange));
    }
    root.appendChild(sectionEl);
  }
}

function renderFieldsScreen(screen, values) {
  const root = document.querySelector(`[data-screen-sections='${screen}']`);
  if (!root) return;
  root.replaceChildren();
  const config = SCREEN_CONFIG[screen];

  const sectionEl = document.createElement("section");
  sectionEl.className = "screen-section";
  for (const field of config.fields) {
    const current = values[field.key];
    const onChange = (val) => { values[field.key] = val; };
    sectionEl.appendChild(buildFieldRow(screen, field, current, onChange));
  }
  root.appendChild(sectionEl);
}

function renderRowsScreen(screen, values) {
  const root = document.querySelector(`[data-screen-rows='${screen}']`);
  if (!root) return;
  root.replaceChildren();
  const config = SCREEN_CONFIG[screen];
  const list = values[config.list_key] || (values[config.list_key] = []);

  list.forEach((row, index) => {
    const rowEl = document.createElement("div");
    rowEl.className = "screen-row";
    rowEl.dataset.rowIndex = String(index);

    for (const column of config.columns) {
      const wrapper = document.createElement("div");
      wrapper.className = "screen-row-cell";
      const labelEl = document.createElement("label");
      const labelText = document.createElement("span");
      labelText.className = "screen-row-label";
      labelText.textContent = column.label;
      const marker = buildScreenInfoMarker(screen, column.key);
      const labelHeader = document.createElement("span");
      labelHeader.className = "screen-row-label-header";
      labelHeader.appendChild(labelText);
      const currency = fieldCurrency(screen, column.key);
      if (currency) {
        const tag = document.createElement("span");
        tag.className = "currency-tag";
        tag.textContent = currency;
        labelHeader.appendChild(tag);
      }
      if (marker) labelHeader.appendChild(marker);
      labelEl.appendChild(labelHeader);

      const onChange = (val) => { row[column.key] = val; };
      if (currency && column.widget === "number") {
        const wrap = document.createElement("span");
        wrap.className = "input-with-currency";
        const prefix = document.createElement("span");
        prefix.className = "currency-prefix";
        prefix.textContent = currency === "USD" ? "$" : (currency === "EUR" ? "€" : "");
        wrap.appendChild(prefix);
        wrap.appendChild(buildScreenInput(column, row[column.key], onChange));
        const pill = document.createElement("span");
        pill.className = "currency";
        pill.textContent = currency;
        wrap.appendChild(pill);
        labelEl.appendChild(wrap);
      } else {
        labelEl.appendChild(buildScreenInput(column, row[column.key], onChange));
      }
      wrapper.appendChild(labelEl);
      rowEl.appendChild(wrapper);
    }

    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "row-remove-button";
    removeButton.textContent = "Remove";
    removeButton.addEventListener("click", () => {
      const wasPending = !rowHasAnyValue(list[index]);
      list.splice(index, 1);
      renderRowsScreen(screen, values);
      // Removing a saved (non-pending) row triggers an immediate save so
      // the deletion is durable. Removing a pending row that never made
      // it to disk does not need a save.
      if (!wasPending) {
        autosaveSchedule(screen, { immediate: true });
      }
    });
    rowEl.appendChild(removeButton);
    root.appendChild(rowEl);
  });

  if (list.length === 0) {
    const empty = document.createElement("p");
    empty.className = "screen-rows-empty";
    empty.textContent = "No rows yet — click \"Add\" to start.";
    root.appendChild(empty);
  }
}

function renderScreenMeta(screen) {
  const target = document.querySelector(`[data-screen-meta='${screen}']`);
  if (!target) return;
  target.replaceChildren();
  const progress = screenUiState.progress;
  if (!progress) return;
  const screenInfo = (progress.screens && progress.screens[screen]) || null;
  if (screenInfo && screenInfo.last_saved_at) {
    const stamp = document.createElement("span");
    stamp.className = "screen-meta-stamp";
    stamp.textContent = `Last saved: ${screenInfo.last_saved_at}`;
    target.appendChild(stamp);
  }
}

function renderScreen(screen) {
  const config = SCREEN_CONFIG[screen];
  if (!config) return;
  const values = screenUiState.values[screen] || {};
  screenUiState.values[screen] = values;

  if (config.kind === "person_blocks") {
    renderIdentityScreen(values);
  } else if (config.kind === "fields") {
    renderFieldsScreen(screen, values);
  } else if (config.kind === "rows") {
    renderRowsScreen(screen, values);
  }
  renderScreenMeta(screen);
}

async function loadScreen(screen) {
  const validation = document.querySelector(`[data-screen-validation='${screen}']`);
  if (validation) validation.textContent = "";
  try {
    await fetchScreenMetadata();
    await fetchScreenState(screen);
    await fetchProgress();
    renderScreen(screen);
  } catch (error) {
    if (validation) validation.textContent = String(error);
  }
}

function rowHasAnyValue(row) {
  if (!row || typeof row !== "object") return false;
  for (const value of Object.values(row)) {
    if (value === true) return true;
    if (typeof value === "string" && value.trim() !== "") return true;
    if (typeof value === "number" && !Number.isNaN(value)) return true;
  }
  return false;
}

function buildScreenPayload(screen) {
  const values = screenUiState.values[screen] || {};
  const config = SCREEN_CONFIG[screen];
  if (config.kind === "person_blocks") {
    // Send only persons that have at least one populated field, but always
    // include the wrapper objects so partial-save still hits the right
    // shape on the server.
    return {
      taxpayer: values.taxpayer || {},
      spouse: values.spouse || {},
    };
  }
  if (config.kind === "rows") {
    // Skip "pending" rows that the user added but hasn't filled. The row
    // becomes part of the saved list as soon as it has any value.
    const rawRows = values[config.list_key] || [];
    const filtered = rawRows.filter(rowHasAnyValue);
    return { [config.list_key]: filtered };
  }
  // "fields"
  const out = {};
  for (const field of config.fields) {
    if (field.widget === "checkbox") {
      out[field.key] = values[field.key] === true || values[field.key] === "true";
    } else {
      out[field.key] = values[field.key] ?? "";
    }
  }
  return out;
}

function bindScreenForm(screen) {
  const form = document.querySelector(`[data-screen-form='${screen}']`);
  if (!form) return;

  // Saver coalesces the current screen state into a POST. We skip empty
  // rows for repeated-row screens (see buildScreenPayload).
  registerScreenSaver(screen, async () => {
    const body = buildScreenPayload(screen);
    const response = await postScreenState(screen, body);
    renderJson(`${screen}-output`, response);
    await fetchProgress();
    // Update only the meta strip (e.g., "Last saved at ..."), NOT the
    // full form — that would lose focus on the active input.
    renderScreenMeta(screen);
    return response;
  });

  attachAutosaveListeners(form, screen);

  // Submit button is now a "Save now" override. Manual click clears the
  // pending debounce timer and POSTs immediately.
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    autosaveSaveNow(screen);
  });

  for (const button of document.querySelectorAll(`[data-nav-target='${screen}']`)) {
    button.addEventListener("click", () => {
      loadScreen(screen);
    });
  }

  for (const button of document.querySelectorAll(`[data-add-row='${screen}']`)) {
    button.addEventListener("click", () => {
      const config = SCREEN_CONFIG[screen];
      const values = screenUiState.values[screen] || {};
      screenUiState.values[screen] = values;
      const list = values[config.list_key] || (values[config.list_key] = []);
      const blank = {};
      for (const column of config.columns) blank[column.key] = "";
      list.push(blank);
      // Re-render to show the new blank row, but do NOT trigger a save —
      // the row is "pending" until the user fills at least one field.
      renderScreen(screen);
    });
  }
}

function bindAllScreenForms() {
  for (const screen of SCREEN_NAMES) {
    bindScreenForm(screen);
  }
}

async function saveAllProgress() {
  const status = document.getElementById("save-all-status");
  const button = document.getElementById("save-all-button");
  if (button) button.disabled = true;
  if (status) status.textContent = "Saving…";
  try {
    const screens = {};
    for (const screen of SCREEN_NAMES) {
      if (screenUiState.loaded[screen]) {
        screens[screen] = buildScreenPayload(screen);
      }
    }
    const response = await apiRequest("/api/save-all", {
      method: "POST",
      body: JSON.stringify({
        year: state.year,
        workspace: state.workspace,
        screens,
      }),
    });
    if (response.progress) {
      screenUiState.progress = response.progress;
      renderProgressSummary();
    }
    if (status) {
      status.classList.add("is-success");
      status.textContent = `Saved ${Object.keys(response.saved || {}).length} screens.`;
      setTimeout(() => {
        if (status) {
          status.classList.remove("is-success");
          status.textContent = "";
        }
      }, 3000);
    }
  } catch (error) {
    if (status) status.textContent = String(error);
  } finally {
    if (button) button.disabled = false;
  }
}

function bindSaveAllButton() {
  const button = document.getElementById("save-all-button");
  if (!button) return;
  button.addEventListener("click", () => {
    saveAllProgress();
  });
}

window.addEventListener("DOMContentLoaded", () => {
  initializeWorkspaceYearDefault();
  bindNavigation();
  bindQuickStartCards();
  bindWorkspaceForm();
  bindHouseholdForm();
  bindPaymentsForm();
  bindUploadForm();
  bindReadinessButton();
  bindRunButton();
  bindOutputsButton();
  bindPosturesScreen();
  bindAllScreenForms();
  bindSaveAllButton();
  bindOutputPreviewModal();
  // Initial stepper state: all sections (except Workspace) are locked
  // until the user opens or creates a workspace via a quick-start card
  // or the Switch-workspace flow.
  setStepperLocked(true);
  setStepStatus("workspace", "new");
  setStepperCurrent("workspace");
});
