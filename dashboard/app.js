const $ = (id) => document.getElementById(id);
const state = {
  config: null,
  trips: [],
  data: null,
  tripId: null,
  view: "overview",
  caseId: null,
  evidenceId: null,
  breakmeId: null,
  pendingAction: null,
  uploadedUrl: null,
};

const VIEW_TITLES = {
  overview: ["COORDINATOR VIEW", "Trip overview"],
  inbox: ["REVIEW QUEUE", "Exceptions inbox"],
  trail: ["RECORD HISTORY", "Evidence trail"],
  claims: ["EXPORT", "Claim sheet"],
  audit: ["INTEGRITY", "Audit check"],
  breakme: ["DEMO STATION", "Break-me station"],
};

const PREPARED = [
  { evidenceId: "SYN-E-CAL-005", label: "Exact resend", expectation: "Same ticket ID and same image bytes. A duplicate must not count twice." },
  { evidenceId: "SYN-E-CAL-006", label: "Cropped resend", expectation: "Same ticket after a small crop. Similarity is a signal; inspect the shared ticket ID." },
  { evidenceId: "SYN-E-CAL-014", label: "Out-of-window ticket", expectation: "Ticket date is outside the synthetic trip window; send to review." },
  { evidenceId: "SYN-E-TEST-021", label: "Pending payment, no ticket", expectation: "Open a case after the configured wait; do not imply that a ticket was issued." },
  { evidenceId: "SYN-E-TEST-027", label: "Suspicious refund message", expectation: "Classify as SUSPECT_NOTICE and request human review." },
];

function esc(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]);
}

async function request(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
  });
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("application/json") ? await response.json() : await response.text();
  if (!response.ok) throw new Error(body?.error || `Request failed (${response.status})`);
  return body;
}

function toast(message) {
  const target = $("toast");
  target.textContent = message;
  target.classList.add("show");
  window.clearTimeout(toast.timer);
  toast.timer = window.setTimeout(() => target.classList.remove("show"), 2800);
}

function relationshipTag(type) {
  const klass = String(type || "UNMATCHED").toLowerCase();
  return `<span class="relationship-tag ${esc(klass)}">${esc(type || "UNMATCHED")}</span>`;
}

function relationFrom(row) { return row.from_evidence_id || row.from_id || ""; }
function relationTo(row) { return row.to_evidence_id || row.to_id || ""; }

function readable(value) {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function line(label, value) {
  return `<div class="record-line"><dt>${esc(label)}</dt><dd>${esc(readable(value))}</dd></div>`;
}

function shortId(id) {
  return String(id || "").replace(/^SYN-E-/, "").replaceAll("-", " · ");
}

function displayAction(action) {
  return ({ approve: "Coordinator approved", proof_requested: "Evidence requested", reject: "Coordinator rejected", manual_link: "Linked manually" })[action] || String(action || "Decision").replaceAll("_", " ");
}

function setView(view) {
  state.view = view;
  document.querySelectorAll(".nav-link").forEach((button) => button.classList.toggle("active", button.dataset.view === view));
  document.querySelectorAll(".view-section").forEach((section) => {
    const active = section.id === `view-${view}`;
    section.hidden = !active;
    section.classList.toggle("active", active);
  });
  const [kicker, title] = VIEW_TITLES[view] || VIEW_TITLES.overview;
  $("page-kicker").textContent = kicker;
  $("page-title").textContent = title;
  if (view === "audit") refreshAudit();
  if (view === "claims") refreshClaims();
  if (view === "trail") renderTrail();
}

function renderTripPicker() {
  const select = $("trip-select");
  select.replaceChildren();
  state.trips.forEach((trip) => {
    const option = document.createElement("option");
    option.value = trip.trip_id;
    option.textContent = `${trip.split === "heldout" ? "Held-out" : "Calibration"} · ${trip.service_date}`;
    select.append(option);
  });
  select.value = state.tripId;
}

async function loadTrip(tripId) {
  state.tripId = tripId;
  state.data = await request(`/api/data?trip_id=${encodeURIComponent(tripId)}`);
  if (!state.caseId || !state.data.cases.some((row) => row.case_id === state.caseId)) {
    state.caseId = state.data.cases[0]?.case_id || null;
  }
  if (!state.evidenceId || !state.data.records.some((row) => row.evidence_id === state.evidenceId)) {
    state.evidenceId = state.data.records[0]?.evidence_id || null;
  }
  renderAll();
}

function renderAll() {
  if (!state.data) return;
  const isFixture = state.data.mode === "fixture";
  $("mode-pill").innerHTML = `<span></span>${isFixture ? "SYNTHETIC FIXTURES" : "LIVE MEMBER B API"}`;
  $("mode-pill").classList.toggle("live", !isFixture);
  $("fixture-banner").innerHTML = isFixture
    ? `<strong>DEMO DATA</strong><span>These examples are hand-authored. They do not measure real extraction accuracy or coordinator time.</span>`
    : `<strong>LIVE API</strong><span>Records come from Member B's API. The local demo chain and prepared break-me items remain synthetic.</span>`;
  $("footer-trip").textContent = `${state.tripId} · ${isFixture ? "FIXTURE" : "LIVE API"}`;
  $("trip-date").textContent = `Service date · ${state.data.trip_window?.service_date || "Synthetic"}`;
  $("nav-case-count").textContent = state.data.cases.length;
  $("inbox-count").textContent = `${state.data.cases.length} cases`;
  $("roster-count").textContent = `${state.data.roster.length} travellers`;
  renderSummary();
  renderRoster();
  renderInbox();
  renderTrailPicker();
  renderTrail();
  renderBreakme();
  if (state.view === "claims") refreshClaims();
  if (state.view === "audit") refreshAudit();
}

function renderSummary() {
  const summary = state.data.summary;
  const metrics = [
    ["Travellers in fixture", summary.traveller_count, "Pseudonymous synthetic senders"],
    ["Evidence items", summary.evidence_count, "All sample images carry a synthetic label"],
    ["Ticket screenshots", summary.ticket_screenshots, "A screenshot is a claim, not a travel record"],
    ["Cases to review", summary.review_cases, "Examples prepared for the coordinator view"],
  ];
  $("summary-metrics").innerHTML = metrics.map(([label, value, note]) => `<div class="metric"><span class="metric-label">${esc(label)}</span><strong class="metric-value">${esc(value)}</strong><p class="metric-note">${esc(note)}</p></div>`).join("");
}

function renderRoster() {
  const body = $("roster-table").querySelector("tbody");
  body.innerHTML = state.data.roster.map((traveller) => {
    const types = traveller.relationship_types.map(relationshipTag).join("");
    return `<tr>
      <td><span class="traveller-name">${esc(traveller.display_name)}</span><span class="sub-cell">${esc(traveller.evidence_count)} evidence items</span></td>
      <td class="${traveller.payment_seen ? "status-yes" : "status-no"}">${traveller.payment_seen ? "Seen" : "Not seen"}</td>
      <td class="${traveller.ticket_seen ? "status-yes" : "status-no"}">${traveller.ticket_seen ? "Seen" : "Not seen"}</td>
      <td>${types}</td>
      <td class="state-text">${esc(traveller.observed_state)}</td>
      <td class="status-no">${esc(traveller.travel_assertion)}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="6" class="empty-state">No evidence in this fixture trip.</td></tr>`;
}

function recordMap() {
  const normalized = state.data.records.map((record) => {
    const fields = record.ground_truth_fields || record.fields || record.interpretation?.fields || {};
    return {
      ...record,
      screenshot_type: record.screenshot_type || record.interpretation?.screenshot_type || "OTHER",
      ground_truth_fields: fields,
      labels: record.labels || [],
    };
  });
  return new Map(normalized.map((record) => [record.evidence_id, record]));
}

function renderInbox() {
  const list = $("case-list");
  const cases = state.data.cases;
  list.innerHTML = `<div class="case-list-heading">${cases.length} SYNTHETIC CASES</div>` + (cases.map((item) => `
    <button class="case-row ${item.case_id === state.caseId ? "selected" : ""}" data-case="${esc(item.case_id)}">
      <span class="case-row-title"><span>${esc(item.title)}</span>${relationshipTag(item.relationship_type)}</span>
      <p>${esc(item.reason)}</p>
      <span class="case-row-meta"><span class="small-copy">${esc(item.decision_support.replaceAll("_", " "))}</span><span class="small-copy">${esc(item.evidence_ids.length)} items</span></span>
    </button>`).join("") || `<div class="empty-state">No fixture cases in this trip.</div>`);
  list.querySelectorAll("[data-case]").forEach((button) => button.addEventListener("click", () => {
    state.caseId = button.dataset.case;
    renderInbox();
  }));

  const selected = cases.find((item) => item.case_id === state.caseId);
  const detail = $("case-detail");
  if (!selected) {
    detail.innerHTML = `<div class="empty-state">Select a case to see its reason and evidence items.</div>`;
    return;
  }
  const map = recordMap();
  const evidence = selected.evidence_ids.map((id) => map.get(id) || RECORD_FALLBACK(id)).filter(Boolean);
  const localDecisions = state.data.decisions.filter((decision) => decision.case_id === selected.case_id);
  const levels = Object.entries(selected.evidence_levels || {}).map(([key, value]) => `<span class="attribute-level"><strong>${esc(key.replaceAll("_", " "))}</strong> · ${esc(value.replaceAll("_", " "))}</span>`).join("");
  detail.innerHTML = `
    <div class="case-detail-top"><div><p class="eyebrow">${esc(selected.case_id)} · ${esc(state.tripId)}</p><h3>${esc(selected.title)}</h3></div>${relationshipTag(selected.relationship_type)}</div>
    <p class="case-detail-reason">${esc(selected.reason)}</p>
    <p class="eyebrow">EVIDENCE LEVEL BY ATTRIBUTE</p><div class="attribute-levels">${levels || `<span class="attribute-level">No attribute level supplied</span>`}</div>
    <p class="eyebrow">RELATED EVIDENCE</p>
    <div class="case-evidence">${evidence.map((record) => `<button class="evidence-chip" data-open-trail="${esc(record.evidence_id)}"><span><code>${esc(record.evidence_id)}</code> · ${esc(record.screenshot_type)}</span><span aria-hidden="true">Open trail →</span></button>`).join("")}</div>
    ${localDecisions.length ? `<div class="decision-list"><strong>Local fixture actions</strong>${localDecisions.map((decision) => `<div>${esc(displayAction(decision.action))} · ${esc(decision.created_at)}</div>`).join("")}</div>` : ""}
    <div class="case-actions">
      <button class="button button-soft" data-action="approve">Approve claim</button>
      <button class="button button-outline" data-action="proof_requested">Request evidence</button>
      <button class="button button-warn" data-action="reject">Reject claim</button>
      <button class="button button-outline" data-action="manual_link">Link manually</button>
    </div>`;
  detail.querySelectorAll("[data-open-trail]").forEach((button) => button.addEventListener("click", () => {
    state.evidenceId = button.dataset.openTrail;
    renderTrailPicker();
    setView("trail");
  }));
  detail.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", () => openDecision(selected, button.dataset.action)));
}

function RECORD_FALLBACK(id) {
  return { evidence_id: id, screenshot_type: "Evidence", ground_truth_fields: {} };
}

function renderTrailPicker() {
  const select = $("trail-select");
  const current = state.evidenceId;
  select.replaceChildren();
  state.data.records.forEach((record) => {
    const option = document.createElement("option");
    option.value = record.evidence_id;
    option.textContent = `${record.evidence_id} · ${record.screenshot_type}`;
    select.append(option);
  });
  if (state.data.records.some((record) => record.evidence_id === current)) select.value = current;
}

async function renderTrail() {
  if (!state.data || !state.evidenceId) return;
  const listRecord = recordMap().get(state.evidenceId);
  if (!listRecord) return;
  $("trail-select").value = state.evidenceId;
  let trail;
  try {
    trail = await request(`/api/trail/${encodeURIComponent(state.evidenceId)}`);
  } catch (error) {
    $("record-grid").innerHTML = `<div class="panel empty-state">${esc(error.message)}</div>`;
    return;
  }
  const record = trail.record || { ...(trail.evidence || {}), screenshot_type: trail.interpretation?.screenshot_type };
  const interpretation = trail.interpretation || {};
  const fields = interpretation.fields || record.ground_truth_fields || record.fields || listRecord.ground_truth_fields || {};
  const relationRows = trail.relationships || state.data.relationships.filter((row) => state.evidenceId === relationFrom(row) || state.evidenceId === relationTo(row));
  const relatedDecision = trail.decisions || state.data.decisions.filter((row) => (row.evidence_ids || []).includes(state.evidenceId));
  const fixtureMode = state.data.mode === "fixture";
  if (!record.evidence_id) record.evidence_id = state.evidenceId;
  if (!record.screenshot_type) record.screenshot_type = listRecord.screenshot_type;
  $("trail-header").innerHTML = `<div><h3>${esc(record.evidence_id)} · ${esc(record.screenshot_type)}</h3><p>${esc(record.sender_id || "No sender in fixture")} · ${esc(record.received_at || "")}</p></div><div>${relationRows.map((row) => relationshipTag(row.type)).join("") || relationshipTag("UNMATCHED")}</div>`;
  const evidenceLines = [
    ["Evidence ID", record.evidence_id], ["Trip", record.trip_id], ["Sender", record.sender_id],
    ["Channel", record.channel || trail.evidence?.channel], ["Received at", record.received_at || trail.evidence?.received_at], ["SHA-256", record.sha256 || trail.evidence?.sha256],
    ["pHash", record.phash || trail.evidence?.phash], ["aHash", record.ahash || trail.evidence?.ahash],
  ];
  const nonNullFields = Object.entries(fields).filter(([, value]) => value !== null && value !== undefined);
  const rawImageControl = fixtureMode && record.image_file
    ? `<button class="button button-outline" id="reveal-image">View synthetic screenshot</button><div id="raw-image-slot"></div><p>An image is fetched only after this explicit request. The access is logged in this local demo session.</p>`
    : `<p class="small-copy">Raw images are hidden in the coordinator view. Connect B's logged-access action before enabling image access.</p>`;
  const producer = fixtureMode ? "Hand-authored synthetic label" : (interpretation.producer || "Member A extractor");
  const modelVersion = fixtureMode ? "Not a model output" : (interpretation.model_version || "Not supplied");
  $("record-grid").innerHTML = `
    <section class="panel record-panel"><h3>Evidence <span>WHAT WAS SENT</span></h3><dl class="record-lines">${evidenceLines.map(([key, value]) => line(key, value)).join("")}</dl><div class="raw-image-frame">${rawImageControl}</div></section>
    <section class="panel record-panel"><h3>Interpretation <span>WHAT WAS READ</span></h3><dl class="record-lines">${line("Producer", producer)}${line("Model version", modelVersion)}${line("Screenshot type", interpretation.screenshot_type || record.screenshot_type)}${line("Type confidence", fixtureMode ? "Fixture label, not a confidence score" : interpretation.type_confidence)}${line("Language", interpretation.language_detected || fields.language_detected)}${nonNullFields.map(([key, value]) => line(key, value)).join("")}</dl><p class="small-copy">${fixtureMode ? "Ground-truth fields are displayed for demo wiring. They are not extraction predictions." : "Extracted values remain separate from the evidence and any coordinator decision."}</p></section>
    <section class="panel record-panel"><h3>Relationship <span>WHY ITEMS ARE RELATED</span></h3>${relationRows.length ? relationRows.map((row) => `<div class="relation-detail">${relationshipTag(row.type)}<dl class="record-lines">${line("Other evidence", relationFrom(row) === record.evidence_id ? relationTo(row) : relationFrom(row))}${line("Basis", (row.basis || []).join(", ") || "Insufficient basis")}${line("Reason", row.reason)}${line("Auto-clear eligible", row.auto_clear_eligible ? "Only if no other flag" : "No")}</dl></div>`).join("") : `<p class="muted">No relationship record is supplied for this item; it remains unmatched in the fixture.</p>`}</section>
    <section class="panel record-panel"><h3>Decision <span>WHAT A HUMAN DECIDED</span></h3>${relatedDecision.length ? `<dl class="record-lines">${relatedDecision.map((decision) => `${line("Action", displayAction(decision.action))}${line("Decided by", decision.decided_by)}${line("Reason", decision.reason || "No reason entered")}${line("Snapshot hash", decision.seen_snapshot_hash)}${line("Created at", decision.created_at)}`).join("")}</dl>` : `<p class="muted">No coordinator decision is recorded in this fixture session.</p>`}</section>`;
  $("reveal-image")?.addEventListener("click", async () => {
    try {
      const response = await fetch(`/api/fixture/raw-image/${encodeURIComponent(record.evidence_id)}`);
      if (!response.ok) throw new Error("Image could not be opened.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      $("raw-image-slot").innerHTML = `<img src="${url}" alt="Synthetic screenshot for ${esc(record.evidence_id)}">`;
      toast("Synthetic image opened; request logged.");
      refreshAccessLog();
    } catch (error) {
      toast(error.message);
    }
  });
}

function openDecision(item, action) {
  state.pendingAction = { caseId: item.case_id, action };
  const titles = { approve: "Approve claim", proof_requested: "Request more evidence", reject: "Reject claim", manual_link: "Link evidence manually" };
  $("decision-title").textContent = titles[action] || "Record a decision";
  $("decision-context").textContent = `${item.case_id} · ${item.title}`;
  $("decision-reason").value = "";
  const linkRow = $("manual-link-row");
  linkRow.hidden = action !== "manual_link";
  if (action === "manual_link") {
    const select = $("manual-target");
    select.replaceChildren();
    const already = new Set(item.evidence_ids);
    state.data.records.filter((record) => !already.has(record.evidence_id)).forEach((record) => {
      const option = document.createElement("option");
      option.value = record.evidence_id;
      option.textContent = `${record.evidence_id} · ${record.screenshot_type}`;
      select.append(option);
    });
  }
  $("decision-dialog").showModal();
}

async function submitDecision(event) {
  event.preventDefault();
  if (event.submitter?.value === "cancel" || !state.pendingAction) return $("decision-dialog").close();
  const payload = {
    case_id: state.pendingAction.caseId,
    subject_ref: state.pendingAction.caseId,
    action: state.pendingAction.action,
    reason: $("decision-reason").value,
  };
  const selectedCase = state.data.cases.find((row) => row.case_id === payload.case_id);
  const currentMap = recordMap();
  const snapshot = {
    case: selectedCase,
    evidence: (selectedCase?.evidence_ids || []).map((id) => currentMap.get(id)).filter(Boolean),
    relationships: state.data.relationships.filter((row) => (selectedCase?.evidence_ids || []).some((id) => id === relationFrom(row) || id === relationTo(row))),
  };
  try {
    const canonical = stableStringify(snapshot);
    const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(canonical));
    payload.seen_snapshot_hash = Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
  } catch {
    return toast("This browser cannot create the decision snapshot hash.");
  }
  if (payload.action === "manual_link") payload.link_to_evidence_id = $("manual-target").value;
  try {
    await request("/api/decisions", { method: "POST", body: JSON.stringify(payload) });
    $("decision-dialog").close();
    await loadTrip(state.tripId);
    toast("Local fixture decision recorded for this session.");
  } catch (error) {
    toast(error.message);
  }
}

function stableStringify(value) {
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  if (value && typeof value === "object") {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(",")}}`;
  }
  return JSON.stringify(value);
}

async function refreshClaims() {
  if (!state.tripId) return;
  try {
    const result = await request(`/api/claims/preview?trip_id=${encodeURIComponent(state.tripId)}`);
    const table = $("claims-table");
    table.querySelector("thead").innerHTML = `<tr>${result.headers.map((header) => `<th>${esc(header.replaceAll("_", " "))}</th>`).join("")}</tr>`;
    table.querySelector("tbody").innerHTML = result.rows.map((row) => `<tr>${row.map((value) => `<td>${esc(value)}</td>`).join("")}</tr>`).join("");
  } catch (error) {
    toast(error.message);
  }
}

async function refreshAudit() {
  try {
    const [audit, access] = await Promise.all([request("/api/audit/verify"), request("/api/access-log")]);
    const status = $("audit-status");
    const fixtureAudit = audit.mode === "synthetic_fixture_chain";
    status.innerHTML = `<div class="audit-status-top"><span class="audit-indicator ${audit.valid ? "" : "broken"}">${audit.valid ? "✓" : "!"}</span><div><p class="eyebrow">${esc((audit.mode || (fixtureAudit ? "synthetic fixture chain" : "Member B audit API")).replaceAll("_", " "))}</p><h3>${audit.valid ? "Chain links agree" : "A record hash does not match"}</h3></div></div><p>${esc(audit.record_count ?? "Audit API")} ${fixtureAudit ? "synthetic records checked" : "records checked"}${audit.first_broken_record ? `. First mismatch: ${esc(audit.first_broken_record)}` : ". No mismatched link was reported."}</p>`;
    $("audit-action-note").textContent = fixtureAudit ? (audit.valid ? "The fixture chain is intact." : `Mismatch located at ${audit.first_broken_record}.`) : "The chain status above comes from Member B's audit endpoint.";
    $("tamper-button").disabled = !fixtureAudit;
    $("reset-audit").disabled = !fixtureAudit;
    $("access-count").textContent = `${access.items.length} requests`;
    $("access-log-list").innerHTML = access.items.length ? access.items.map((entry) => `<div class="access-log-row"><span>${esc(entry.evidence_id)} · ${esc(entry.reason)}</span><time>${esc(entry.requested_at)}</time></div>`).join("") : `<p class="muted">No synthetic image has been opened in this session.</p>`;
  } catch (error) {
    $("audit-status").textContent = error.message;
  }
}

function renderBreakme() {
  const map = recordMap();
  const list = $("breakme-list");
  list.innerHTML = PREPARED.map((sample) => {
    const record = map.get(sample.evidenceId) || (state.allRecords || []).find((row) => row.evidence_id === sample.evidenceId);
    const selected = sample.evidenceId === state.breakmeId;
    return `<button class="sample-option ${selected ? "selected" : ""}" data-sample="${esc(sample.evidenceId)}"><strong>${esc(sample.label)}</strong><span>${esc(record?.screenshot_type || "fixture")} · ${esc(shortId(sample.evidenceId))}</span></button>`;
  }).join("");
  list.querySelectorAll("[data-sample]").forEach((button) => button.addEventListener("click", () => {
    state.breakmeId = button.dataset.sample;
    renderBreakme();
  }));
  $("attempt-count").textContent = `${PREPARED.length} prepared examples`;
  $("attempt-log").innerHTML = PREPARED.map((sample) => `<div class="attempt-row"><span>${esc(sample.label)}</span><span class="relationship-tag">Expected handling</span></div>`).join("");
  $("attempt-count").setAttribute("aria-label", `${PREPARED.length} prepared examples; no model outcomes`);
  const sample = PREPARED.find((entry) => entry.evidenceId === state.breakmeId) || PREPARED[0];
  if (!sample) return;
  state.breakmeId = sample.evidenceId;
  const record = state.allRecords?.find((row) => row.evidence_id === sample.evidenceId) || map.get(sample.evidenceId);
  if (!record) {
    $("breakme-preview").innerHTML = `<div class="empty-state">This prepared screenshot belongs to the other fixture trip. Switch trips to view it.</div>`;
    return;
  }
  const labels = (record.labels || []).map((label) => label.replaceAll("_", " ")).join(" · ");
  $("breakme-preview").innerHTML = `<div class="sample-preview-header"><div><p class="eyebrow">${esc(record.evidence_id)} · ${esc(record.screenshot_type)}</p><h3>${esc(sample.label)}</h3></div><span class="count-label">Fixture expectation</span></div><p>${esc(sample.expectation)}</p><p><strong>Authored fixture label:</strong> ${esc(labels || "no special label")}</p><p class="small-copy">This is the expected handling from the ground truth file, not a classifier result.</p><button class="button button-outline" id="breakme-image">Reveal synthetic screenshot</button><div id="breakme-image-slot"></div>`;
  $("breakme-image").addEventListener("click", async () => {
    try {
      const response = await fetch(`/api/fixture/raw-image/${encodeURIComponent(record.evidence_id)}`);
      if (!response.ok) throw new Error("Image could not be opened.");
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      $("breakme-image-slot").innerHTML = `<img src="${url}" alt="Synthetic ${esc(record.screenshot_type)} sample">`;
      refreshAccessLog();
    } catch (error) { toast(error.message); }
  });
}

function setUploadMessage(file) {
  $("upload-state").innerHTML = `Selected locally: <strong>${esc(file.name)}</strong>. No file was sent. The intake/classifier service is not connected.`;
}

function setExports() {
  $("export-top").addEventListener("click", () => download("csv"));
  $("export-csv").addEventListener("click", () => download("csv"));
  $("export-xlsx").addEventListener("click", () => download("xlsx"));
}

function download(format) {
  const extension = format === "xlsx" ? "xlsx" : "csv";
  window.location.href = `/api/export/claims.${extension}?trip_id=${encodeURIComponent(state.tripId)}`;
}

async function init() {
  try {
    state.config = await request("/api/config");
    const trips = await request("/api/trips");
    state.trips = trips.items;
    state.tripId = state.trips.some((trip) => trip.trip_id === state.config.trip_id) ? state.config.trip_id : state.trips.at(-1)?.trip_id;
    renderTripPicker();
    await loadTrip(state.tripId);
    state.allRecords = (await request("/api/fixture/records")).items;
    renderBreakme();
    $("trip-select").addEventListener("change", (event) => loadTrip(event.target.value).catch((error) => toast(error.message)));
    $("trail-select").addEventListener("change", (event) => { state.evidenceId = event.target.value; renderTrail(); });
    document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
    document.querySelectorAll("[data-go]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.go)));
    $("decision-form").addEventListener("submit", submitDecision);
    $("tamper-button").addEventListener("click", async () => {
      await request("/api/audit/tamper", { method: "POST", body: "{}" });
      await refreshAudit();
      toast("The fixture chain now shows a mismatch.");
    });
    $("reset-audit").addEventListener("click", async () => {
      await request("/api/audit/reset", { method: "POST", body: "{}" });
      await refreshAudit();
      toast("The synthetic fixture chain was reset.");
    });
    $("judge-upload").addEventListener("change", (event) => {
      if (event.target.files?.[0]) setUploadMessage(event.target.files[0]);
    });
    setExports();
    renderBreakme();
  } catch (error) {
    document.body.innerHTML = `<main style="max-width:720px;margin:10vh auto;padding:24px;font:16px Segoe UI,sans-serif;color:#17273b"><h1>Dashboard could not load</h1><p>${esc(error.message)}</p><p>Start the local fixture server from the repository root: <code>python dashboard/server.py</code></p></main>`;
  }
}

init();
