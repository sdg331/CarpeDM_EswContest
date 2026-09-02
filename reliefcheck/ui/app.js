const statePill = document.querySelector("#statePill");
const message = document.querySelector("#message");
const householdText = document.querySelector("#householdText");
const itemText = document.querySelector("#itemText");
const decisionText = document.querySelector("#decisionText");
const resultBox = document.querySelector("#resultBox");
const resultTitle = document.querySelector("#resultTitle");
const resultDetail = document.querySelector("#resultDetail");
const householdButtons = document.querySelector("#householdButtons");
const itemButtons = document.querySelector("#itemButtons");
const inventory = document.querySelector("#inventory");
const transactions = document.querySelector("#transactions");
const visionToggle = document.querySelector("#visionToggle");
const connectionBadge = document.querySelector("#connectionBadge");
const deviceHealth = document.querySelector("#deviceHealth");

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

function fmtTime(raw) {
  if (!raw) return "-";
  const date = new Date(raw);
  if (Number.isNaN(date.getTime())) return raw;
  return date.toLocaleTimeString("ko-KR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function setStepClasses(session) {
  const householdStep = document.querySelector("#householdStep");
  const itemStep = document.querySelector("#itemStep");
  const decisionStep = document.querySelector("#decisionStep");
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
    const result = session.last_decision.result;
    decisionStep.classList.add(result === "APPROVED" ? "is-complete" : "is-error");
  } else if (session.item) {
    decisionStep.classList.add("is-active");
  }
}

function renderDashboard(data) {
  const session = data.session;
  statePill.textContent = session.state;
  message.textContent = session.message;

  householdText.textContent = session.household
    ? `${session.household.household_id} · ${session.household.head_name} · ${session.household.member_count}인`
    : "대기 중";

  itemText.textContent = session.item
    ? `${session.item.item_id} · ${session.item.item_name || session.item.item_type}`
    : "대기 중";

  if (session.last_decision) {
    const decision = session.last_decision;
    resultTitle.textContent = decision.result === "APPROVED" ? "승인" : "거절";
    decisionText.textContent = `${decision.reason_code} · ${decision.reason_message}`;
    resultDetail.textContent = decision.receipt_available
      ? `${decision.reason_code} · 지급확인증 출력 완료`
      : `${decision.reason_code} · ${decision.reason_message}`;
    resultBox.classList.toggle("approved", decision.result === "APPROVED");
    resultBox.classList.toggle("rejected", decision.result !== "APPROVED");
  } else {
    resultTitle.textContent = "대기";
    decisionText.textContent = "대기 중";
    resultDetail.textContent = "정책 엔진 판정 전입니다.";
    resultBox.classList.remove("approved", "rejected");
  }

  setStepClasses(session);
  renderInventory(data.inventory || []);
  renderTransactions(data.recent_transactions || []);
}

function renderInventory(rows) {
  inventory.innerHTML = rows
    .map(
      (row) => `
        <div class="inventory-item">
          <div>
            <strong>${row.name}</strong>
            <span>${row.item_type} · 한도 ${row.limit_value}${row.allocation_unit === "person" ? "개/인" : "개/가구"}</span>
          </div>
          <div class="stock-count">${row.available} / ${row.available + row.distributed}</div>
        </div>
      `,
    )
    .join("");
}

function renderTransactions(rows) {
  if (rows.length === 0) {
    transactions.innerHTML = `<tr><td colspan="4">거래 기록 없음</td></tr>`;
    return;
  }

  transactions.innerHTML = rows
    .map(
      (row) => `
        <tr>
          <td>${fmtTime(row.created_at)}</td>
          <td>${row.household_id || "-"}</td>
          <td>${row.item_name || row.item_id || "-"}</td>
          <td class="${row.result === "APPROVED" ? "tx-approved" : "tx-rejected"}">${row.result}</td>
        </tr>
      `,
    )
    .join("");
}

function renderScanButtons(tags) {
  householdButtons.innerHTML = tags.households
    .map(
      (row) => `
        <button class="scan-button" type="button" data-reader="household" data-uid="${row.card_uid}">
          ${row.household_id} · ${row.head_name}
          <small>${row.card_uid} · ${row.status}</small>
        </button>
      `,
    )
    .join("");

  itemButtons.innerHTML = tags.items
    .map(
      (row) => `
        <button class="scan-button" type="button" data-reader="item" data-uid="${row.tag_uid}">
          ${row.name} · ${row.item_id}
          <small>${row.tag_uid} · ${row.status}</small>
        </button>
      `,
    )
    .join("");
}

async function scan(reader, uid) {
  try {
    const data = await post("/api/scan", {
      reader,
      uid,
      vision_verified: visionToggle.checked,
    });
    renderDashboard(data);
    await refreshTags();
  } catch (error) {
    connectionBadge.textContent = "API 오류";
    connectionBadge.classList.remove("badge-ok");
    console.error(error);
  }
}

async function refreshDashboard() {
  const data = await api("/api/state");
  renderDashboard(data);
  await refreshHealth();
  connectionBadge.textContent = "로컬 DB 연결";
  connectionBadge.classList.add("badge-ok");
}

async function refreshTags() {
  const tags = await api("/api/sample-tags");
  renderScanButtons(tags);
}

async function refreshHealth() {
  const health = await api("/health");
  renderHealth(health);
}

function renderHealth(health) {
  const devices = health.devices || {};
  const rows = [
    ["NFC", devices.nfc],
    ["Printer", devices.printer],
    ["Camera", devices.camera],
  ];
  deviceHealth.innerHTML = rows
    .map(([label, device]) => {
      const ok = device && device.ok;
      const mode = device ? device.mode : "unknown";
      return `
        <div class="device-chip ${ok ? "ok" : "bad"}">
          <strong>${label}</strong>
          <span>${ok ? "정상" : "확인 필요"} · ${mode}</span>
        </div>
      `;
    })
    .join("");
}

document.body.addEventListener("click", (event) => {
  const button = event.target.closest("[data-reader][data-uid]");
  if (!button) return;
  scan(button.dataset.reader, button.dataset.uid);
});

document.querySelector("#resetSession").addEventListener("click", async () => {
  renderDashboard(await post("/api/reset"));
});

document.querySelector("#resetData").addEventListener("click", async () => {
  renderDashboard(await post("/api/seed/reset"));
  await refreshTags();
});

function updateClock() {
  document.querySelector("#clock").textContent = new Date().toLocaleTimeString("ko-KR");
}

setInterval(updateClock, 1000);

async function boot() {
  updateClock();
  await refreshTags();
  await refreshDashboard();
}

boot().catch((error) => {
  connectionBadge.textContent = "서버 연결 실패";
  connectionBadge.classList.remove("badge-ok");
  console.error(error);
});
