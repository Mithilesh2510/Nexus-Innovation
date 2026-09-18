// Application Entry Point and Coordinator
// Load branches and categories metadata
async function loadMetadata() {
  try {
    const [branches, categories] = await Promise.all([
      api("/api/branches"),
      api("/api/categories")
    ]);
    state.branchesList = branches;
    state.categoriesList = categories;

    const bSel = document.getElementById("branchFilter");
    branches.forEach(b => {
      const opt = document.createElement("option");
      opt.value = b.branch_id;
      opt.textContent = `${b.branch_id} — ${b.name}`;
      bSel.appendChild(opt);
    });

    const cSel = document.getElementById("categoryFilter");
    categories.forEach(c => {
      const opt = document.createElement("option");
      opt.value = c;
      opt.textContent = c;
      cSel.appendChild(opt);
    });
  } catch(e) {
    console.warn("Metadata load failed", e);
  }
}

// Load executive summary KPIs
async function loadSummary() {
  try {
    const s = await api("/api/dashboard/summary");
    document.getElementById("kpiPairs").textContent = s.total_branch_sku_pairs;
    document.getElementById("kpiCritical").textContent = s.risk_tier_counts.Critical;
    document.getElementById("kpiHigh").textContent = s.risk_tier_counts.High;
    document.getElementById("kpiStockout").textContent = s.avg_stockout_probability_pct + "%";
    document.getElementById("kpiOverdue").textContent = s.total_overdue_incoming_units.toLocaleString();
    document.getElementById("kpiExpiry").textContent = Math.round(s.total_projected_expiry_waste_units).toLocaleString();
    document.getElementById("kpiExpirySub").textContent = `~$${Math.round(s.total_expiry_value).toLocaleString()} potential loss`;
    document.getElementById("headerLiveStatus").textContent = `${s.total_branch_sku_pairs} Nodes Monitored • Live`;
  } catch(e) {
    console.warn("Summary load error", e);
  }
}

// Tabs Switching
document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-pane").forEach(p => p.classList.remove("active"));
    btn.classList.add("active");
    const pane = document.getElementById("tab-" + btn.dataset.tab);
    if (pane) pane.classList.add("active");
  });
});

// Audit Report Modal
const auditModalBtn = document.getElementById("auditModalBtn");
if (auditModalBtn) {
  auditModalBtn.addEventListener("click", async () => {
    const modal = document.getElementById("auditModal");
    modal.style.display = "flex";
    const body = document.getElementById("auditModalBody");
    try {
      const a = await api("/api/audit/summary");
      body.innerHTML = `
        <div class="kpi-row" style="grid-template-columns:repeat(3, 1fr); margin-bottom:20px;">
          <div class="kpi-card ${a.compliance_status === 'OPTIMAL' ? 'safe' : 'critical'}">
            <div class="kpi-label">Health &amp; Compliance</div>
            <div class="kpi-value">${a.system_health_score}/100</div>
            <div class="kpi-sub">${a.compliance_status}</div>
          </div>
          <div class="kpi-card critical">
            <div class="kpi-label">Critical SKUs Value</div>
            <div class="kpi-value">$${a.critical_skus_inventory_value.toLocaleString()}</div>
            <div class="kpi-sub">${a.critical_skus_count} SKUs at Critical Risk</div>
          </div>
          <div class="kpi-card high">
            <div class="kpi-label">Projected Expiry Loss</div>
            <div class="kpi-value">$${a.projected_expiry_loss_value.toLocaleString()}</div>
            <div class="kpi-sub">${a.overdue_incoming_units.toLocaleString()} overdue units</div>
          </div>
        </div>

        <div style="font-weight:700; font-size:13px; margin-bottom:8px; color:var(--text);">Top Priority Recommended Transfers:</div>
        <div style="margin-bottom:20px;">
          ${a.immediate_transfers.map(t => `
            <div style="background:var(--panel-elevated); padding:8px 12px; border-radius:6px; margin-bottom:6px; font-size:12px; border:1px solid var(--border); display:flex; justify-content:space-between;">
              <span><strong>${t.from_branch} → ${t.to_branch}</strong>: ${t.name} (${t.suggested_units} units)</span>
              <span style="color:var(--cyan); font-family:var(--font-mono);">${t.to_branch_stockout_probability_pct}% stockout risk averted</span>
            </div>
          `).join("")}
        </div>

        <div style="font-weight:700; font-size:13px; margin-bottom:8px; color:var(--text);">Executive Action Sign-Off:</div>
        <p style="font-size:12px; color:var(--text-muted); margin-bottom:16px;">
          This audit record reflects deterministic statistical models evaluated at ${a.audit_timestamp}. All simulations utilize quantile block-bootstrapped demand distributions and vendor lead-time Monte Carlo iterations.
        </p>
        <div style="display:flex; justify-content:flex-end; gap:10px;">
          <button class="secondary" onclick="window.print()">Print Report</button>
          <button onclick="document.getElementById('auditModal').style.display='none'">Close</button>
        </div>
      `;
    } catch(e) {
      body.innerHTML = `<div style="color:var(--critical); padding:20px;">Failed to generate audit report: ${e.message}</div>`;
    }
  });
}

const closeAuditModalBtn = document.getElementById("closeAuditModalBtn");
if (closeAuditModalBtn) {
  closeAuditModalBtn.addEventListener("click", () => {
    document.getElementById("auditModal").style.display = "none";
  });
}

// Sync Engine / Refresh Button
const refreshBtn = document.getElementById("refreshBtn");
if (refreshBtn) {
  refreshBtn.addEventListener("click", async () => {
    const icon = document.getElementById("refreshIcon");
    if (icon) icon.style.animation = "spin 1s linear infinite";
    try {
      await api("/api/refresh", { method: "POST" });
      await Promise.all([loadSummary(), loadRiskTable(), loadTransfers()]);
      showToast("Monte Carlo risk engine refreshed!");
    } catch(e) {
      showToast("Refresh error: " + e.message, true);
    } finally {
      if (icon) icon.style.animation = "";
    }
  });
}

// Global Search & Filters Debounce
let searchTimer = null;
const searchInput = document.getElementById("globalSearchInput");
if (searchInput) {
  searchInput.addEventListener("input", () => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(loadRiskTable, 250);
  });
}

document.getElementById("branchFilter")?.addEventListener("change", loadRiskTable);
document.getElementById("categoryFilter")?.addEventListener("change", loadRiskTable);
document.getElementById("critFilter")?.addEventListener("change", loadRiskTable);

// Keyboard shortcut '/' to search
document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement.tagName !== "INPUT") {
    e.preventDefault();
    document.getElementById("globalSearchInput")?.focus();
  }
});

// App Initialization
(async function init() {
  await loadMetadata();
  await loadSummary();
  await loadRiskTable();
  loadTransfers();
  loadSuppliers();
  loadValidation();
  loadDispatchedTransfersLog();
})();
