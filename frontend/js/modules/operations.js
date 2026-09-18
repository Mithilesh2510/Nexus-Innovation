// Operations Module: Inter-facility transfers and procurement PO optimization
// Tab 1: Transfers
async function loadTransfers() {
  const el = document.getElementById("transfersList");
  try {
    const list = await api("/api/transfers");
    document.getElementById("transferBadgeCount").textContent = list.length;
    if (list.length === 0) {
      el.innerHTML = `<div style="color:var(--text-dim); padding:30px; grid-column:1/-1; text-align:center;">No inter-facility transfer opportunities at this moment.</div>`;
      return;
    }

    el.innerHTML = list.slice(0, 18).map((t) => `
      <div class="transfer-card">
        <div class="transfer-head">
          <div class="transfer-lane">
            <span>${t.from_branch}</span>
            <span class="arrow">→</span>
            <span>${t.to_branch}</span>
          </div>
          <span class="risk-pill High">${t.to_branch_stockout_probability_pct}% Shortfall Risk</span>
        </div>
        <div style="font-weight:700; font-size:13.5px; color:var(--text);">${t.name}</div>
        <div class="transfer-body">${t.rationale}</div>
        <div class="transfer-foot">
          <span style="font-family:var(--font-mono); font-size:12px; color:var(--cyan); font-weight:600;">
            ${t.suggested_units} units transferable
          </span>
          <button class="action-btn" onclick="dispatchTransfer('${t.medicine_id}', '${t.from_branch}', '${t.to_branch}', ${t.suggested_units}, this)">
            Dispatch Transfer
          </button>
        </div>
      </div>
    `).join("");
  } catch(e) {
    el.innerHTML = `<div style="color:var(--critical); padding:20px;">Failed to load transfers: ${e.message}</div>`;
  }
}

async function dispatchTransfer(medicine_id, from_branch, to_branch, units, btnEl) {
  try {
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.textContent = "Dispatching…";
    }
    const res = await api("/api/transfers/dispatch", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ medicine_id, from_branch, to_branch, units })
    });
    showToast(res.message);
    loadTransfers();
    loadSummary();
    loadRiskTable();
    loadDispatchedTransfersLog();
  } catch(e) {
    if (btnEl) {
      btnEl.disabled = false;
      btnEl.textContent = "Dispatch Transfer";
    }
    showToast("Transfer dispatch failed: " + e.message, true);
  }
}

async function loadDispatchedTransfersLog() {
  try {
    const log = await api("/api/transfers/history");
    const el = document.getElementById("dispatchedTransfersLog");
    if (!log || log.length === 0) return;
    el.innerHTML = `
      <table>
        <thead>
          <tr><th>ID</th><th>Timestamp</th><th>Medicine</th><th>Route</th><th>Units</th><th>Status</th></tr>
        </thead>
        <tbody>
          ${log.slice().reverse().map(l => `
            <tr>
              <td class="num-mono" style="color:var(--cyan);">${l.transfer_id}</td>
              <td style="color:var(--text-muted);">${l.timestamp}</td>
              <td style="font-weight:600;">${l.medicine_name}</td>
              <td class="num-mono">${l.from_branch} → ${l.to_branch}</td>
              <td class="num-mono">${l.units}</td>
              <td><span class="risk-pill Low">${l.status}</span></td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch(e) {}
}

const reloadTransfersBtn = document.getElementById("reloadTransfersBtn");
if (reloadTransfersBtn) {
  reloadTransfersBtn.addEventListener("click", loadTransfers);
}

// Tab 2: Procurement
const loadProcurementBtn = document.getElementById("loadProcurementBtn");
if (loadProcurementBtn) {
  loadProcurementBtn.addEventListener("click", async () => {
    const budget = document.getElementById("budgetInput").value;
    const wrap = document.getElementById("procurementTableWrap");
    wrap.innerHTML = `<div style="padding:30px; text-align:center; color:var(--text-dim);">Optimizing purchase allocations…</div>`;

    try {
      let path = "/api/procurement/recommendations?top_n=40";
      if (budget) path += `&budget=${budget}`;
      const res = await api(path);
      state.currentRecommendations = res.recommendations;

      document.getElementById("spendSub").textContent = `Est Spend: $${res.total_estimated_spend.toLocaleString()}`;
      if (res.recommendations.length === 0) {
        wrap.innerHTML = `<div style="padding:30px; text-align:center; color:var(--text-dim);">No procurement orders required under current stock levels.</div>`;
        return;
      }

      wrap.innerHTML = `
        <table>
          <thead>
            <tr>
              <th style="width:30px;"><input type="checkbox" id="selectAllPo" checked></th>
              <th>Medicine &amp; Category</th>
              <th>Facility</th>
              <th>Criticality</th>
              <th>Risk Score</th>
              <th>Recommended Units</th>
              <th>Unit Cost</th>
              <th>Est Cost</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>
            ${res.recommendations.map((r, i) => `
              <tr>
                <td><input type="checkbox" class="po-checkbox" data-idx="${i}" checked></td>
                <td><span style="font-weight:600;">${r.name}</span> <span style="color:var(--text-dim); font-size:11px;">(${r.category})</span></td>
                <td class="num-mono">${r.branch_id}</td>
                <td><span class="risk-pill ${r.criticality === 'Critical' ? 'Critical' : 'High'}">${r.criticality}</span></td>
                <td class="num-mono">${r.composite_risk_score}</td>
                <td class="num-mono" style="font-weight:700; color:var(--cyan);">${r.recommended_order_units.toLocaleString()}</td>
                <td class="num-mono">$${r.unit_cost.toFixed(2)}</td>
                <td class="num-mono">$${r.estimated_cost.toLocaleString()}</td>
                <td>
                  <button class="action-btn" onclick="dispatchSinglePo(${i}, this)">Create PO</button>
                </td>
              </tr>
            `).join("")}
          </tbody>
        </table>
      `;

      document.getElementById("selectAllPo")?.addEventListener("change", e => {
        document.querySelectorAll(".po-checkbox").forEach(cb => cb.checked = e.target.checked);
      });
    } catch(e) {
      wrap.innerHTML = `<div style="color:var(--critical); padding:20px;">Failed to calculate recommendations: ${e.message}</div>`;
    }
  });
}

async function dispatchSinglePo(idx, btnEl) {
  const r = state.currentRecommendations[idx];
  if (!r) return;
  try {
    const res = await api("/api/procurement/order", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        medicine_id: r.medicine_id,
        branch_id: r.branch_id,
        units: r.recommended_order_units,
        unit_cost: r.unit_cost
      })
    });
    showToast(`PO Created: ${res.order.order_id} (${res.order.ordered_units} units)`);
    if (btnEl) {
      btnEl.disabled = true;
      btnEl.textContent = "Dispatched";
      btnEl.style.opacity = "0.5";
    }
    loadSummary();
  } catch(e) {
    showToast("PO creation failed: " + e.message, true);
  }
}

const dispatchAllPoBtn = document.getElementById("dispatchAllPoBtn");
if (dispatchAllPoBtn) {
  dispatchAllPoBtn.addEventListener("click", async () => {
    const checkboxes = document.querySelectorAll(".po-checkbox:checked");
    if (checkboxes.length === 0) {
      showToast("Please select at least one purchase order.", true);
      return;
    }
    let count = 0;
    for (const cb of checkboxes) {
      const idx = parseInt(cb.dataset.idx);
      const r = state.currentRecommendations[idx];
      if (r) {
        try {
          await api("/api/procurement/order", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              medicine_id: r.medicine_id,
              branch_id: r.branch_id,
              units: r.recommended_order_units,
              unit_cost: r.unit_cost
            })
          });
          count++;
        } catch (err) {
          console.warn(`Failed to dispatch PO for ${r.name}`, err);
        }
      }
    }
    showToast(`Successfully dispatched ${count} Purchase Orders!`);
    loadSummary();
    if (loadProcurementBtn) loadProcurementBtn.click();
  });
}

const exportPoCsvBtn = document.getElementById("exportPoCsvBtn");
if (exportPoCsvBtn) {
  exportPoCsvBtn.addEventListener("click", () => {
    if (!state.currentRecommendations || state.currentRecommendations.length === 0) {
      showToast("No recommendations to export.", true);
      return;
    }
    const headers = ["Medicine_ID", "Name", "Category", "Branch", "Criticality", "Units", "Unit_Cost", "Estimated_Cost"];
    const rows = state.currentRecommendations.map(r => [
      r.medicine_id, `"${r.name}"`, `"${r.category}"`, r.branch_id, r.criticality, r.recommended_order_units, r.unit_cost, r.estimated_cost
    ]);
    const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows.map(e => e.join(","))].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", `Procurement_Orders_${new Date().toISOString().slice(0, 10)}.csv`);
    document.body.appendChild(link);
    link.click();
    link.remove();
    showToast("Procurement orders CSV exported!");
  });
}
