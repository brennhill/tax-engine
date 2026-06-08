const defaultTaxYear = String(new Date().getFullYear() - 1);

const state = {
  year: defaultTaxYear,
  workspace: "",
  csrfToken: "",
};

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
  renderJson("workspace-output", payload);
  return payload;
}

async function loadWorkspace(year, workspace) {
  const params = new URLSearchParams({ year, workspace });
  const payload = await apiRequest(`/api/workspace?${params.toString()}`);
  renderJson("workspace-output", payload);
  return payload;
}

async function saveHousehold(payload) {
  const response = await apiRequest("/api/intake/household", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderJson("household-output", response);
  return response;
}

async function savePayments(payload) {
  const response = await apiRequest("/api/intake/payments", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderJson("payments-output", response);
  return response;
}

async function uploadDocument(payload) {
  const response = await apiRequest("/api/uploads", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  renderJson("documents-output", response);
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
  const target = document.getElementById("run-output");
  if (!target) return;
  target.textContent = "";
  const heading = document.createElement("p");
  heading.className = "run-progress-heading";
  heading.textContent = `Run ${runId} started — streaming progress…`;
  target.appendChild(heading);
  const list = document.createElement("ol");
  list.className = "run-progress-list";
  list.id = "run-progress-list";
  target.appendChild(list);
}

function renderRunProgress(payload, startedAtMs) {
  const list = document.getElementById("run-progress-list");
  if (!list) return;
  list.replaceChildren();
  const events = Array.isArray(payload.events) ? payload.events : [];
  // Reduce events to per-stage entries: one row per stage_started, with
  // the stage's status updated when stage_completed arrives. This gives
  // the user a stable list that grows as the pipeline progresses.
  const byStage = new Map();
  for (const event of events) {
    if (event.event === "stage_started" && event.stage_id) {
      byStage.set(event.stage_id, {
        stage_id: event.stage_id,
        started_at: event.ts,
        elapsed_seconds: event.elapsed_seconds || 0,
        completed: false,
        completed_elapsed: null,
        phase: event.phase || "",
      });
    } else if (event.event === "stage_completed" && event.stage_id) {
      const entry = byStage.get(event.stage_id);
      if (entry) {
        entry.completed = true;
        entry.completed_elapsed = event.elapsed_seconds || 0;
      }
    }
  }
  for (const entry of byStage.values()) {
    const item = document.createElement("li");
    item.className = entry.completed
      ? "run-stage is-complete"
      : "run-stage is-running";
    const label = document.createElement("span");
    label.className = "run-stage-id";
    label.textContent = entry.stage_id;
    item.appendChild(label);
    if (entry.phase) {
      const phase = document.createElement("span");
      phase.className = "run-stage-phase";
      phase.textContent = ` (${entry.phase})`;
      item.appendChild(phase);
    }
    const timing = document.createElement("span");
    timing.className = "run-stage-timing";
    if (entry.completed) {
      const dt = (entry.completed_elapsed - entry.elapsed_seconds).toFixed(2);
      timing.textContent = ` — ${dt}s`;
    } else {
      const elapsed = ((Date.now() - startedAtMs) / 1000 - entry.elapsed_seconds).toFixed(1);
      timing.textContent = ` — running ${elapsed}s`;
    }
    item.appendChild(timing);
    list.appendChild(item);
  }
  // Status indicator above the list.
  const heading = list.previousElementSibling;
  if (heading && heading.classList.contains("run-progress-heading")) {
    if (payload.status === "running" && payload.current_stage_id) {
      heading.textContent = `Running stage: ${payload.current_stage_id}`;
    } else if (payload.status === "completed") {
      heading.textContent = "Run complete — opening Outputs.";
    } else if (payload.status === "failed") {
      heading.textContent = "Run failed — see error card below.";
    } else {
      heading.textContent = "Run started — streaming progress…";
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
}

function bindNavigation() {
  for (const button of document.querySelectorAll("[data-nav-target]")) {
    button.addEventListener("click", () => showScreen(button.dataset.navTarget));
  }
}

function bindWorkspaceForm() {
  const form = document.getElementById("workspace-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const year = String(formData.get("year") || state.year);
    const workspace = String(formData.get("workspace") || "");
    try {
      await createWorkspace(year, workspace);
      await loadWorkspace(year, workspace);
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

function bindUploadForm() {
  const form = document.getElementById("document-upload-form");
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const file = formData.get("document");
    if (!(file instanceof File) || !file.name) {
      renderJson("documents-output", { error: "Choose a file first." });
      return;
    }
    try {
      await uploadDocument({
        year: state.year,
        workspace: state.workspace,
        filename: file.name,
        content_base64: await fileToBase64(file),
        manual_bucket: String(formData.get("manual_bucket") || ""),
        evidence_only: Boolean(formData.get("evidence_only")),
      });
    } catch (error) {
      renderJson("documents-output", { error: String(error) });
    }
  });
}

function bindReadinessButton() {
  const button = document.getElementById("readiness-button");
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
});
