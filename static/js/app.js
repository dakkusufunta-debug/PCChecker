const ICONS = {
  CPU: "⚡", RAM: "🧠", GPU: "🎮", "ストレージ": "💾",
  "ディスプレイ": "🖥️", "ネットワーク": "🌐", "マザーボード": "📋",
};
const STATUS_LABEL = { below: "基準以下", meets: "この基準OK", exceeds: "基準超え" };

let currentData = null;
let currentProfile = "mid";

async function startAnalysis() {
  show("loading-section");
  hide("start-section");
  hide("error-section");
  hide("result-section");

  try {
    const res = await fetch("/api/analyze");
    const data = await res.json();

    if (!res.ok || data.error) {
      showError(data.message || "スペック取得に失敗しました。");
      return;
    }

    renderResult(data);
  } catch (e) {
    showError("サーバーへの接続に失敗しました: " + e.message);
  }
}

function renderResult(data) {
  currentData = data;
  currentProfile = data.default_profile || "mid";

  renderSysinfo(data.specs);
  setupProfileTabs();

  // 初回描画（アニメーションなし）
  _applyProfileDom(currentProfile);

  show("result-section");
  hide("loading-section");

  // バーアニメーション
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const p = currentData.profiles[currentProfile];
      animateBars(p.overall.score, p.scores);
    });
  });
}

function setupProfileTabs() {
  document.querySelectorAll(".profile-tab").forEach(btn => {
    btn.addEventListener("click", () => applyProfile(btn.dataset.profile));
  });
}

function applyProfile(key) {
  currentProfile = key;

  // タブのアクティブ状態を更新
  document.querySelectorAll(".profile-tab").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.profile === key);
  });

  _applyProfileDom(key);

  // バーを0にリセットしてから再アニメーション
  document.querySelectorAll(".score-bar-fill, .comp-bar-fill").forEach(el => {
    el.style.transition = "none";
    el.style.width = "0%";
  });
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      document.querySelectorAll(".score-bar-fill, .comp-bar-fill").forEach(el => {
        el.style.transition = "width 0.8s ease";
      });
      const p = currentData.profiles[key];
      animateBars(p.overall.score, p.scores);
    });
  });
}

function _applyProfileDom(key) {
  const p = currentData.profiles[key];
  document.getElementById("profile-desc").textContent = p.description;
  renderOverall(p.overall);
  renderComponents(p.scores);
}

function renderOverall(overall) {
  const gradeEl = document.getElementById("grade-circle");
  gradeEl.className = `grade-circle grade-${overall.grade}`;
  document.getElementById("grade-letter").textContent = overall.grade;
  document.getElementById("overall-label").textContent = overall.label;
  document.getElementById("overall-score-val").textContent = overall.score;
  document.getElementById("overall-message").textContent = overall.message;

  const pList = document.getElementById("priority-list");
  pList.innerHTML = "";
  if (overall.priority_upgrades.length > 0) {
    const label = document.createElement("span");
    label.style.cssText = "font-size:0.83rem;color:var(--text-muted);margin-right:6px;";
    label.textContent = "優先アップグレード:";
    pList.appendChild(label);
    overall.priority_upgrades.forEach(name => {
      const tag = document.createElement("span");
      tag.className = "priority-tag";
      tag.textContent = name;
      pList.appendChild(tag);
    });
  }
}

function renderSysinfo(specs) {
  const items = [
    { label: "OS",             value: specs.os_name || "不明" },
    { label: "CPU",            value: specs.cpu_name || "不明" },
    { label: "コア / スレッド", value: `${specs.cpu_cores}コア / ${specs.cpu_threads}スレッド` },
    { label: "クロック",        value: specs.cpu_base_ghz ? `${specs.cpu_base_ghz} GHz (base)` : "不明" },
    { label: "RAM 合計",        value: specs.ram_total_gb ? `${specs.ram_total_gb} GB` : "不明" },
    { label: "RAM 種別",        value: specs.ram_type || "不明" },
    { label: "GPU",            value: specs.gpu_name || "不明" },
    { label: "VRAM",           value: specs.gpu_vram_gb ? `${specs.gpu_vram_gb} GB` : "不明" },
    { label: "マザーボード",    value: specs.motherboard || "不明" },
    { label: "チップセット",    value: specs.mb_chipset || "不明" },
    {
      label: "ディスプレイ",
      value: specs.display_width
        ? `${specs.display_width}×${specs.display_height} / ${specs.display_refresh_hz}Hz`
        : "不明",
    },
    { label: "有線LAN", value: specs.network_wired_mbps ? `${specs.network_wired_mbps}Mbps` : "なし" },
    { label: "Wi-Fi",   value: specs.network_wifi_standard || "なし" },
  ];

  if (specs.storage_list && specs.storage_list.length > 0) {
    specs.storage_list.forEach((s, i) => {
      const type  = s.is_nvme ? "NVMe SSD" : (s.is_ssd ? "SATA SSD" : "HDD");
      const label = i === 0 ? "ストレージ1" : `ストレージ${i + 1}`;
      items.push({ label, value: `${s.size_gb}GB ${type}` });
    });
  }

  const grid = document.getElementById("sysinfo-grid");
  grid.innerHTML = items.map(i => `
    <div class="sysinfo-item">
      <div class="sysinfo-label">${i.label}</div>
      <div class="sysinfo-value">${i.value}</div>
    </div>
  `).join("");
}

function renderComponents(scores) {
  const grid = document.getElementById("components-grid");
  grid.innerHTML = scores.map(s => buildComponentCard(s)).join("");
}

function buildComponentCard(s) {
  const icon        = ICONS[s.name] || "🔧";
  const statusLabel = STATUS_LABEL[s.status] || s.status;

  const recs = s.recommendations.length > 0
    ? `<div class="recommendations">
        ${s.recommendations.map(r => `<div class="rec-item">${r}</div>`).join("")}
       </div>`
    : "";

  const upgrades = s.upgrade_options.length > 0
    ? `<div class="upgrade-section">
        <div class="upgrade-title">🛒 おすすめパーツ</div>
        <div class="upgrade-list">
          ${s.upgrade_options.map(u => `
            <div class="upgrade-item">
              <span class="upgrade-name">${u.name}</span>
              <span class="upgrade-price">${u.price}</span>
              <span class="upgrade-note">${u.note}</span>
            </div>
          `).join("")}
        </div>
       </div>`
    : "";

  return `
    <div class="component-card status-${s.status}">
      <div class="comp-header">
        <div class="comp-name">
          <span class="comp-icon">${icon}</span>
          ${s.name}
        </div>
        <span class="status-badge ${s.status}">${statusLabel}</span>
      </div>

      <div class="comp-score-row">
        <span class="comp-score-num">${s.score}</span>
        <div class="comp-bar-wrap">
          <div class="comp-bar">
            <div class="comp-bar-fill" data-score="${s.score}" style="width:0%"></div>
          </div>
        </div>
      </div>

      <div class="comp-current">
        <div class="comp-current-label">現在のスペック</div>
        <div class="comp-current-val">${s.current_value}</div>
      </div>

      <div class="comp-standard">${s.midrange_standard}</div>

      ${s.notes ? `<div class="comp-notes">${s.notes}</div>` : ""}

      ${recs}
      ${upgrades}
    </div>
  `;
}

function animateBars(overallScore, scores) {
  const overallBar = document.getElementById("overall-bar");
  if (overallBar) overallBar.style.width = overallScore + "%";

  document.querySelectorAll(".comp-bar-fill").forEach(el => {
    const score = parseInt(el.getAttribute("data-score") || "0", 10);
    el.style.width = score + "%";
  });
}

function showError(msg) {
  document.getElementById("error-message").textContent = msg;
  hide("loading-section");
  hide("start-section");
  show("error-section");
}

function show(id) { document.getElementById(id).classList.remove("hidden"); }
function hide(id) { document.getElementById(id).classList.add("hidden"); }
