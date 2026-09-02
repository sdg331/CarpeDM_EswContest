const $ = (selector) => document.querySelector(selector);

const elements = {
  connectionBadge: $("#connectionBadge"),
  operationState: $("#operationState"),
  clock: $("#clock"),
  metricCards: $("#metricCards"),
  statePill: $("#statePill"),
  message: $("#message"),
  householdText: $("#householdText"),
  itemText: $("#itemText"),
  decisionText: $("#decisionText"),
  resultBox: $("#resultBox"),
  resultTitle: $("#resultTitle"),
  resultDetail: $("#resultDetail"),
  resultMeta: $("#resultMeta"),
  householdButtons: $("#householdButtons"),
  itemButtons: $("#itemButtons"),
  inventory: $("#inventory"),
  visionToggle: $("#visionToggle"),
  dashboardMetrics: $("#dashboardMetrics"),
  inventoryPressure: $("#inventoryPressure"),
  reasonCodes: $("#reasonCodes"),
  auditTransactions: $("#auditTransactions"),
  riskEvents: $("#riskEvents"),
  decisionChecklist: $("#decisionChecklist"),
  decisionContext: $("#decisionContext"),
  policyMatrix: $("#policyMatrix"),
  deviceMatrix: $("#deviceMatrix"),
  deviceHealth: $("#deviceHealth"),
  softwareMode: $("#softwareMode"),
  softwareScore: $("#softwareScore"),
  softwarePillars: $("#softwarePillars"),
  softwareScenarios: $("#softwareScenarios"),
  softwareBoundary: $("#softwareBoundary"),
  softwareLatest: $("#softwareLatest"),
  experimentTargets: $("#experimentTargets"),
};

const appState = {
  dashboard: null,
  health: null,
  ops: null,
  tags: null,
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

function post(path, body = {}) {
  return api(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>"']/g, (char) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[char];
  });
}

function fmtTime(raw) {
  if (!raw) return "-";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return escapeHtml(raw);
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtNumber(value) {
  return Number(value || 0).toLocaleString("ko-KR");
}

function resultLabel(result) {
  return result === "APPROVED" ? "승인" : "거절";
}

function riskLabel(level) {
  if (level === "critical") return "소진";
  if (level === "watch") return "주의";
  return "안정";
}

function evidenceStatusLabel(status) {
  if (status === "ready") return "검증 준비";
  if (status === "watch") return "점검 필요";
  if (status === "needs_measurement") return "실측 필요";
  if (status === "pass") return "통과";
  if (status === "needs_evidence") return "증거 필요";
  if (status === "needs_run") return "실행 필요";
  return status || "대기";
}

function setConnection(ok, label = "로컬 DB 연결") {
  elements.connectionBadge.textContent = ok ? label : "서버 연결 실패";
  elements.connectionBadge.classList.toggle("badge-ok", ok);
  elements.connectionBadge.classList.toggle("badge-bad", !ok);
}

function setStepClasses(session) {
  const householdStep = $("#householdStep");
  const itemStep = $("#itemStep");
  const decisionStep = $("#decisionStep");
  for (const element of [householdStep, itemStep, decisionStep]) {
    element.classList.remove("is-active", "is-complete", "is-error");
  }

  if (session.household) {
    householdStep.classList.add("is-complete");
  } else {
    householdStep.classList.add("is-active");
  }

  if (session.item) {
    itemStep.classList.add("is-complete");
  } else if (session.household) {
    itemStep.classList.add("is-active");
  }

  if (session.last_decision) {
    decisionStep.classList.add(session.last_decision.result === "APPROVED" ? "is-complete" : "is-error");
  } else if (session.item) {
    decisionStep.classList.add("is-active");
  }
}

function renderDashboard(data) {
  appState.dashboard = data;
  const session = data.session || {};
  elements.statePill.textContent = session.state || "WAIT_HOUSEHOLD";
  elements.message.textContent = session.message || "가구 카드를 왼쪽 리더에 태그해 주세요.";

  elements.householdText.textContent = session.household
    ? `${session.household.household_id} · ${session.household.head_name} · ${session.household.member_count}인`
    : "대기 중";

  elements.itemText.textContent = session.item
    ? `${session.item.item_id} · ${session.item.item_name || session.item.item_type}`
    : "대기 중";

  renderDecision(session.last_decision);
  setStepClasses(session);
  renderFieldInventory(data.inventory || []);
  renderAuditTransactions(data.recent_transactions || []);
}

function renderDecision(decision) {
  elements.resultBox.classList.remove("approved", "rejected");
  if (!decision) {
    elements.resultTitle.textContent = "대기";
    elements.decisionText.textContent = "대기 중";
    elements.resultDetail.textContent = "정책 엔진 판정 전입니다.";
    elements.resultMeta.innerHTML = "";
    renderDecisionChecklist(null);
    renderDecisionContext(null);
    return;
  }

  const approved = decision.result === "APPROVED";
  elements.resultTitle.textContent = resultLabel(decision.result);
  elements.decisionText.textContent = `${decision.reason_code} · ${decision.reason_message}`;
  elements.resultDetail.textContent = decision.receipt_available
    ? `${decision.reason_code} · 지급확인증 출력 완료`
    : `${decision.reason_code} · ${decision.reason_message}`;
  elements.resultBox.classList.add(approved ? "approved" : "rejected");
  elements.resultMeta.innerHTML = `
    <div><dt>거래번호</dt><dd>${escapeHtml(decision.transaction_id || "-")}</dd></div>
    <div><dt>출력 상태</dt><dd>${escapeHtml(decision.print_status || "NOT_REQUIRED")}</dd></div>
    <div><dt>확인증</dt><dd>${decision.receipt_available ? "생성됨" : "없음"}</dd></div>
  `;
  renderDecisionChecklist(decision);
  renderDecisionContext(decision.context || null);
}

function renderFieldInventory(rows) {
  if (!rows.length) {
    elements.inventory.innerHTML = `<p class="empty">재고 데이터 없음</p>`;
    return;
  }

  elements.inventory.innerHTML = rows
    .map((row) => {
      const total = Number(row.available || 0) + Number(row.distributed || 0);
      const ratio = total ? Math.round((Number(row.available || 0) / total) * 100) : 0;
      return `
        <div class="inventory-item">
          <div>
            <strong>${escapeHtml(row.name)}</strong>
            <span>${escapeHtml(row.item_type)} · 한도 ${escapeHtml(row.limit_value)}${
              row.allocation_unit === "person" ? "개/인" : "개/가구"
            }</span>
            <div class="mini-bar" aria-hidden="true"><span style="width: ${ratio}%"></span></div>
          </div>
          <div class="stock-count">${fmtNumber(row.available)} / ${fmtNumber(total)}</div>
        </div>
      `;
    })
    .join("");
}

function renderAuditTransactions(rows) {
  if (!rows.length) {
    elements.auditTransactions.innerHTML = `<tr><td colspan="6">거래 기록 없음</td></tr>`;
    return;
  }

  elements.auditTransactions.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${fmtTime(row.created_at)}</td>
          <td>${escapeHtml(row.household_id || "-")}</td>
          <td>${escapeHtml(row.item_name || row.item_id || "-")}</td>
          <td><span class="status-token ${row.result === "APPROVED" ? "approved" : "rejected"}">${escapeHtml(
            resultLabel(row.result),
          )}</span></td>
          <td>${escapeHtml(row.reason_code || "-")}</td>
          <td>${escapeHtml(row.print_status || "-")}</td>
        </tr>
      `,
    )
    .join("");
}

function renderScanButtons(tags) {
  appState.tags = tags;
  elements.householdButtons.innerHTML = tags.households
    .map(
      (row) => `
        <button class="scan-button ${row.status === "ACTIVE" ? "" : "is-blocked"}" type="button" data-reader="household" data-uid="${escapeHtml(row.card_uid)}">
          <span>${escapeHtml(row.household_id)} · ${escapeHtml(row.head_name)}</span>
          <small>${escapeHtml(row.card_uid)} · ${escapeHtml(row.status)} · ${escapeHtml(row.member_count)}인</small>
        </button>
      `,
    )
    .join("");

  elements.itemButtons.innerHTML = tags.items
    .map(
      (row) => `
        <button class="scan-button ${row.status === "READY" ? "" : "is-used"}" type="button" data-reader="item" data-uid="${escapeHtml(
          row.tag_uid,
        )}">
          <span>${escapeHtml(row.name)} · ${escapeHtml(row.item_id)}</span>
          <small>${escapeHtml(row.tag_uid)} · ${escapeHtml(row.status)}</small>
        </button>
      `,
    )
    .join("");
}

function renderHealth(health) {
  appState.health = health;
  const devices = health.devices || {};
  const rows = [
    ["NFC", devices.nfc],
    ["Printer", devices.printer],
    ["Camera", devices.camera],
  ];
  elements.deviceHealth.innerHTML = rows
    .map(([label, device]) => {
      const ok = device && device.ok;
      const mode = device ? device.mode : "unknown";
      return `
        <div class="device-chip ${ok ? "ok" : "bad"}">
          <strong>${escapeHtml(label)}</strong>
          <span>${ok ? "정상" : "확인 필요"} · ${escapeHtml(mode)}</span>
        </div>
      `;
    })
    .join("");
}

function renderOps(ops) {
  appState.ops = ops;
  elements.operationState.textContent = ops.shelter?.operation_state || "상태 확인";
  elements.operationState.classList.toggle("badge-ok", ops.shelter?.operation_state === "운영 가능");
  elements.operationState.classList.toggle("badge-bad", ops.shelter?.operation_state !== "운영 가능");
  renderMetricCards(ops.metrics || {});
  renderDashboardMetrics(ops.metrics || {});
  renderInventoryPressure(ops.inventory_pressure || []);
  renderReasonCodes(ops.reason_codes || []);
  renderRiskEvents(ops.risk_events || []);
  renderPolicyMatrix(ops.policy_matrix || []);
  renderDeviceMatrix(ops.device_matrix || []);
  renderSoftwareEvidence(ops.software_evidence || {});
  renderExperimentTargets(ops.experiment_targets || []);
}

function renderMetricCards(metrics) {
  const cards = [
    ["오늘 거래", fmtNumber(metrics.today_total), "현장 처리량"],
    ["승인", fmtNumber(metrics.approved), `승인율 ${metrics.approval_rate || 0}%`],
    ["중복 차단", fmtNumber(metrics.duplicate_blocks), "D001/D002"],
    ["남은 재고", fmtNumber(metrics.inventory_available), "전체 물품 기준"],
  ];
  elements.metricCards.innerHTML = cards
    .map(
      ([label, value, detail]) => `
        <article class="metric-card">
          <span>${label}</span>
          <strong>${value}</strong>
          <small>${detail}</small>
        </article>
      `,
    )
    .join("");
}

function renderDashboardMetrics(metrics) {
  const rows = [
    ["전체 거래", metrics.total],
    ["오늘 거래", metrics.today_total],
    ["승인 거래", metrics.approved],
    ["거절 거래", metrics.rejected],
    ["지급확인증 출력", metrics.printed],
    ["출력 실패", metrics.print_failed],
    ["활성 가구", metrics.active_households],
    ["지급 완료 재고", metrics.inventory_distributed],
  ];
  elements.dashboardMetrics.innerHTML = rows
    .map(
      ([label, value]) => `
        <div class="dashboard-metric">
          <span>${label}</span>
          <strong>${fmtNumber(value)}</strong>
        </div>
      `,
    )
    .join("");
}

function renderInventoryPressure(rows) {
  if (!rows.length) {
    elements.inventoryPressure.innerHTML = `<p class="empty">재고 데이터 없음</p>`;
    return;
  }
  elements.inventoryPressure.innerHTML = rows
    .map(
      (row) => `
        <div class="pressure-item ${escapeHtml(row.risk_level)}">
          <div>
            <strong>${escapeHtml(row.name)}</strong>
            <span>${escapeHtml(row.item_type)} · ${riskLabel(row.risk_level)}</span>
          </div>
          <div class="pressure-meter">
            <span style="width: ${Number(row.remaining_ratio || 0)}%"></span>
          </div>
          <b>${fmtNumber(row.available)}개</b>
        </div>
      `,
    )
    .join("");
}

function renderReasonCodes(rows) {
  if (!rows.length) {
    elements.reasonCodes.innerHTML = `<p class="empty">아직 판정 코드가 없습니다.</p>`;
    return;
  }
  elements.reasonCodes.innerHTML = rows
    .map(
      (row) => `
        <div class="reason-item">
          <strong>${escapeHtml(row.reason_code)}</strong>
          <span>${escapeHtml(row.reason_message)}</span>
          <b>${fmtNumber(row.count)}건</b>
        </div>
      `,
    )
    .join("");
}

function renderRiskEvents(rows) {
  if (!rows.length) {
    elements.riskEvents.innerHTML = `<p class="empty">주의 이벤트 없음</p>`;
    return;
  }
  elements.riskEvents.innerHTML = rows
    .map(
      (row) => `
        <div class="event-item">
          <span>${fmtTime(row.timestamp)}</span>
          <strong>${escapeHtml(row.code)}</strong>
          <p>${escapeHtml(row.message)}</p>
        </div>
      `,
    )
    .join("");
}

function renderDecisionChecklist(decision) {
  const checks = decision?.checks || [];
  if (!checks.length) {
    elements.decisionChecklist.innerHTML = `<p class="empty">가구와 물품을 태그하면 판정 근거가 표시됩니다.</p>`;
    return;
  }
  elements.decisionChecklist.innerHTML = checks
    .map(
      (check) => `
        <div class="check-item ${escapeHtml(check.status)}">
          <span class="check-state">${check.status === "pass" ? "통과" : "실패"}</span>
          <div>
            <strong>${escapeHtml(check.label)}</strong>
            <p>${escapeHtml(check.detail)}</p>
          </div>
        </div>
      `,
    )
    .join("");
}

function renderDecisionContext(context) {
  if (!context || !Object.keys(context).length) {
    elements.decisionContext.innerHTML = `<div><dt>상태</dt><dd>판정 대기</dd></div>`;
    return;
  }
  const labelMap = {
    household_id: "가구 ID",
    household_status: "가구 상태",
    member_count: "가구원 수",
    item_id: "물품 ID",
    item_type: "물품 유형",
    item_status: "물품 상태",
    requested_quantity: "요청 수량",
    vision_verified: "카메라 일치",
    inventory_available: "남은 재고",
    inventory_distributed: "지급 재고",
    allocation_unit: "지급 단위",
    limit_value: "정책 한도",
    already_received: "기지급 수량",
    allowed_quantity: "허용 수량",
  };
  elements.decisionContext.innerHTML = Object.entries(context)
    .filter(([key]) => labelMap[key])
    .map(
      ([key, value]) => `
        <div>
          <dt>${labelMap[key]}</dt>
          <dd>${escapeHtml(value === true ? "예" : value === false ? "아니오" : value)}</dd>
        </div>
      `,
    )
    .join("");
}

function renderPolicyMatrix(rows) {
  if (!rows.length) {
    elements.policyMatrix.innerHTML = `<p class="empty">정책 데이터 없음</p>`;
    return;
  }
  elements.policyMatrix.innerHTML = rows
    .map(
      (row) => `
        <article class="policy-card">
          <div>
            <span>${escapeHtml(row.item_type)}</span>
            <strong>${escapeHtml(row.name)}</strong>
            <p>${escapeHtml(row.description)}</p>
          </div>
          <dl>
            <div><dt>단위</dt><dd>${row.allocation_unit === "person" ? "개인" : "가구"}</dd></div>
            <div><dt>한도</dt><dd>${fmtNumber(row.limit_value)}개</dd></div>
            <div><dt>재고</dt><dd>${fmtNumber(row.available)}개</dd></div>
          </dl>
        </article>
      `,
    )
    .join("");
}

function renderDeviceMatrix(rows) {
  if (!rows.length) {
    elements.deviceMatrix.innerHTML = `<p class="empty">장치 상태 없음</p>`;
    return;
  }
  elements.deviceMatrix.innerHTML = rows
    .map(
      (row) => `
        <article class="device-card ${row.ok ? "ok" : "bad"}">
          <div>
            <span>${escapeHtml(row.role)}</span>
            <strong>${escapeHtml(row.name)}</strong>
            <p>${escapeHtml(row.mission)}</p>
          </div>
          <dl>
            <div><dt>상태</dt><dd>${row.ok ? "정상" : "점검 필요"}</dd></div>
            <div><dt>모드</dt><dd>${escapeHtml(row.mode)}</dd></div>
            <div><dt>메시지</dt><dd>${escapeHtml(row.message || "-")}</dd></div>
          </dl>
        </article>
      `,
    )
    .join("");
}

function renderExperimentTargets(rows) {
  if (!rows.length) {
    elements.experimentTargets.innerHTML = `<p class="empty">검증 지표 없음</p>`;
    return;
  }
  elements.experimentTargets.innerHTML = rows
    .map(
      (row) => `
        <article class="experiment-item ${escapeHtml(row.status)}">
          <div>
            <span>${escapeHtml(evidenceStatusLabel(row.status))}</span>
            <strong>${escapeHtml(row.name)}</strong>
            <p>${escapeHtml(row.target)}</p>
          </div>
          <dl>
            <div><dt>현재</dt><dd>${escapeHtml(row.current)}</dd></div>
            <div><dt>근거</dt><dd>${escapeHtml(row.evidence)}</dd></div>
          </dl>
        </article>
      `,
    )
    .join("");
}

function renderSoftwareEvidence(evidence) {
  renderSoftwareMode(evidence.mode || {});
  renderSoftwareScore(evidence.readiness || {});
  renderSoftwarePillars(evidence.pillars || []);
  renderSoftwareScenarios(evidence.scenario_coverage || []);
  renderSoftwareBoundary(evidence.hardware_boundary || []);
  renderLatestSuite(evidence.latest_suite || {});
}

function renderSoftwareMode(mode) {
  elements.softwareMode.innerHTML = `
    <div class="mode-card">
      <span>${escapeHtml(mode.name || "SW Evidence Mode")}</span>
      <strong>${mode.hardware_available ? "실장비 포함" : "소프트웨어 검증 모드"}</strong>
      <p>${escapeHtml(mode.position || "정책과 거래 흐름을 소프트웨어로 검증합니다.")}</p>
    </div>
    <p class="boundary-note">${escapeHtml(mode.boundary || "물리 장치 성능은 별도 실측 대상입니다.")}</p>
  `;
}

function renderSoftwareScore(readiness) {
  const score = Number(readiness.score || 0);
  elements.softwareScore.innerHTML = `
    <div class="score-ring" style="--score: ${Math.max(0, Math.min(100, score))}%">
      <strong>${score}%</strong>
      <span>${escapeHtml(readiness.label || "검증 실행 필요")}</span>
    </div>
    <dl class="score-meta">
      <div><dt>획득</dt><dd>${fmtNumber(readiness.earned)}점</dd></div>
      <div><dt>총점</dt><dd>${fmtNumber(readiness.total)}점</dd></div>
    </dl>
  `;
}

function renderSoftwarePillars(rows) {
  if (!rows.length) {
    elements.softwarePillars.innerHTML = `<p class="empty">품질 축 데이터 없음</p>`;
    return;
  }
  elements.softwarePillars.innerHTML = rows
    .map(
      (row) => `
        <article class="pillar-item ${escapeHtml(row.status)}">
          <div>
            <span>${escapeHtml(evidenceStatusLabel(row.status))}</span>
            <strong>${escapeHtml(row.name)}</strong>
            <p>${escapeHtml(row.evidence)}</p>
          </div>
          <dl>
            <div><dt>점수</dt><dd>${fmtNumber(row.earned)} / ${fmtNumber(row.weight)}</dd></div>
            <div><dt>상태</dt><dd>${escapeHtml(row.detail)}</dd></div>
          </dl>
        </article>
      `,
    )
    .join("");
}

function renderSoftwareScenarios(rows) {
  if (!rows.length) {
    elements.softwareScenarios.innerHTML = `<p class="empty">시나리오 데이터 없음</p>`;
    return;
  }
  elements.softwareScenarios.innerHTML = rows
    .map(
      (row) => `
        <article class="scenario-card ${escapeHtml(row.status)}">
          <span>${escapeHtml(row.case_id)}</span>
          <strong>${escapeHtml(row.name)}</strong>
          <p>${escapeHtml(row.purpose)}</p>
          <dl>
            <div><dt>기대</dt><dd>${escapeHtml(row.expected_result)} / ${escapeHtml(row.expected_code)}</dd></div>
            <div><dt>실제</dt><dd>${escapeHtml(formatActualScenario(row.actual))}</dd></div>
          </dl>
        </article>
      `,
    )
    .join("");
}

function formatActualScenario(actual) {
  if (!actual || !Object.keys(actual).length) return "suite 실행 필요";
  return `${actual.result || "-"} / ${actual.reason_code || "-"} / ${actual.print_status || "NOT_REQUIRED"}`;
}

function renderSoftwareBoundary(rows) {
  if (!rows.length) {
    elements.softwareBoundary.innerHTML = `<p class="empty">경계 데이터 없음</p>`;
    return;
  }
  elements.softwareBoundary.innerHTML = rows
    .map(
      (row) => `
        <div class="boundary-item ${row.ok ? "ok" : "bad"}">
          <strong>${escapeHtml(row.name)}</strong>
          <span>${escapeHtml(row.mode)}</span>
          <p>${escapeHtml(row.software_verified)}</p>
          <small>${escapeHtml(row.physical_boundary)}</small>
        </div>
      `,
    )
    .join("");
}

function renderLatestSuite(latest) {
  if (!latest.available) {
    elements.softwareLatest.innerHTML = `<p class="empty">${escapeHtml(latest.message || "suite 실행 결과 없음")}</p>`;
    return;
  }
  const summary = latest.summary || {};
  elements.softwareLatest.innerHTML = `
    <div class="latest-summary">
      <strong>${fmtNumber(summary.passed_cases)} / ${fmtNumber(summary.total_cases)}</strong>
      <span>자동 시나리오 통과</span>
    </div>
    <dl class="score-meta">
      <div><dt>거래</dt><dd>${fmtNumber(summary.transactions)}건</dd></div>
      <div><dt>거절</dt><dd>${fmtNumber(summary.rejected)}건</dd></div>
      <div><dt>출력 실패 격리</dt><dd>${fmtNumber(summary.print_failed)}건</dd></div>
    </dl>
  `;
}

async function scan(reader, uid) {
  try {
    const data = await post("/api/scan", {
      reader,
      uid,
      vision_verified: elements.visionToggle.checked,
    });
    renderDashboard(data);
    await Promise.all([refreshTags(), refreshOps()]);
    setConnection(true);
  } catch (error) {
    setConnection(false);
    console.error(error);
  }
}

async function refreshTags() {
  const tags = await api("/api/sample-tags");
  renderScanButtons(tags);
}

async function refreshHealth() {
  const health = await api("/health");
  renderHealth(health);
}

async function refreshOps() {
  const ops = await api("/api/ops");
  renderOps(ops);
}

async function refreshDashboard() {
  const data = await api("/api/state");
  renderDashboard(data);
}

async function refreshAll() {
  const [tags, dashboard, health, ops] = await Promise.all([
    api("/api/sample-tags"),
    api("/api/state"),
    api("/health"),
    api("/api/ops"),
  ]);
  renderScanButtons(tags);
  renderDashboard(dashboard);
  renderHealth(health);
  renderOps(ops);
  setConnection(true);
}

function activateTab(tabName) {
  document.querySelectorAll(".tab-button").forEach((button) => {
    const active = button.dataset.tabTarget === tabName;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-selected", String(active));
  });
  document.querySelectorAll(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${tabName}`);
  });
}

document.body.addEventListener("click", (event) => {
  const tab = event.target.closest("[data-tab-target]");
  if (tab) {
    activateTab(tab.dataset.tabTarget);
    return;
  }

  const scanButton = event.target.closest("[data-reader][data-uid]");
  if (scanButton) {
    scan(scanButton.dataset.reader, scanButton.dataset.uid);
  }
});

$("#resetSession").addEventListener("click", async () => {
  try {
    renderDashboard(await post("/api/reset"));
    setConnection(true);
  } catch (error) {
    setConnection(false);
    console.error(error);
  }
});

$("#resetData").addEventListener("click", async () => {
  try {
    await post("/api/seed/reset");
    await refreshAll();
  } catch (error) {
    setConnection(false);
    console.error(error);
  }
});

function updateClock() {
  elements.clock.textContent = new Date().toLocaleTimeString("ko-KR");
}

setInterval(updateClock, 1000);
setInterval(() => {
  refreshAll().catch((error) => {
    setConnection(false);
    console.error(error);
  });
}, 10000);

async function boot() {
  updateClock();
  await refreshAll();
}

boot().catch((error) => {
  setConnection(false);
  console.error(error);
});
