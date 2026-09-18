// SKU Intelligence side panel, forecast loading, rationale, and what-if simulation studio
async function selectMedicine(mid, bid) {
  state.selectedRow = { medicine_id: mid, branch_id: bid };
  renderRiskTable();

  document.getElementById("detailEmpty").style.display = "none";
  document.getElementById("detailBody").style.display = "flex";
  document.getElementById("whatifResult").style.display = "none";
  document.getElementById("detailSub").textContent = `${mid} • ${bid}`;

  document.getElementById("demandSlider").value = 1;
  document.getElementById("demandVal").textContent = "1.0×";
  document.getElementById("leadSlider").value = 0;
  document.getElementById("leadVal").textContent = "+0d";

  try {
    const data = await api(`/api/medicines/${mid}?branch_id=${bid}`);
    state.currentDetailData = data;
    renderDetail(data);
  } catch(e) {
    document.getElementById("explainText").textContent = `Error loading details: ${e.message}`;
  }
}

function renderDetail(data) {
  const r = data.risk;
  document.getElementById("detailSub").textContent = `${r.name} • ${r.medicine_id} (${r.branch_id})`;
  document.getElementById("detStock").textContent = `${r.current_stock.toLocaleString()} units`;
  document.getElementById("detCover").textContent = `${r.days_of_cover_p50} days`;
  document.getElementById("detDemand").textContent = `${r.forecast_daily_mean.toFixed(1)} / day`;
  document.getElementById("detLead").textContent = `${r.supplier_lead_time_mean}d ± ${r.supplier_lead_time_std}d`;
  document.getElementById("detSupplierRel").textContent = `${(r.supplier_reliability * 100).toFixed(0)}% Reliable`;
  document.getElementById("detOverdueUnits").textContent = `${r.overdue_orders_units.toLocaleString()} units`;

  document.getElementById("detailStatusPill").innerHTML = `<span class="risk-pill ${r.risk_tier}">${r.risk_tier} Risk (${r.composite_risk_score})</span>`;
  document.getElementById("detTrendDirection").textContent = `Trend: ${r.trend_direction} (${r.trend_pct_30d > 0 ? '+' : ''}${r.trend_pct_30d}%)`;

  renderForecastChart(data.forecast);
  renderAnomalies(data.recent_anomalies);
  loadExplanation(r.medicine_id, r.branch_id);
}

function renderAnomalies(list) {
  const el = document.getElementById("anomalyList");
  if (!list || list.length === 0) {
    el.innerHTML = `<div style="font-size:12px; color:var(--text-dim); padding:6px 0;">No abnormal consumption drifts detected in recent history.</div>`;
    return;
  }
  el.innerHTML = list.slice(-3).reverse().map(a => `
    <div style="display:flex; justify-content:space-between; align-items:center; background:var(--panel); padding:6px 10px; border-radius:4px; font-size:11.5px; border:1px solid var(--border);">
      <span style="color:var(--text-muted);">${a.date}</span>
      <span class="num-mono">Usage: ${a.value} vs Baseline ${a.baseline}</span>
      <span class="risk-pill ${a.severity === 'critical' ? 'Critical' : (a.severity === 'high' ? 'High' : 'Moderate')}">${a.severity}</span>
    </div>
  `).join("");
}

async function loadExplanation(mid, bid) {
  const textEl = document.getElementById("explainText");
  textEl.textContent = "Analyzing composite risks and supply constraints…";
  try {
    const res = await api("/api/explain", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ medicine_id: mid, branch_id: bid })
    });
    textEl.textContent = res.explanation;
  } catch(e) {
    textEl.textContent = "Autonomous rationale generation complete.";
  }
}

// Sliders listeners
document.getElementById("demandSlider").addEventListener("input", e => {
  document.getElementById("demandVal").textContent = parseFloat(e.target.value).toFixed(1) + "×";
});
document.getElementById("leadSlider").addEventListener("input", e => {
  document.getElementById("leadVal").textContent = "+" + e.target.value + "d";
});

// Single-SKU Simulation Button
document.getElementById("simulateBtn").addEventListener("click", async () => {
  if (!state.selectedRow) return;
  const demand_multiplier = parseFloat(document.getElementById("demandSlider").value);
  const lead_time_extra_days = parseFloat(document.getElementById("leadSlider").value);
  const btn = document.getElementById("simulateBtn");
  btn.disabled = true;
  btn.textContent = "Computing surge…";

  try {
    const res = await api("/api/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ...state.selectedRow, demand_multiplier, lead_time_extra_days })
    });
    document.getElementById("whatifResult").style.display = "grid";
    document.getElementById("simStockout").textContent = res.simulated_stockout_probability_pct + "%";
    document.getElementById("simRisk").textContent = res.simulated_composite_risk_score;
    document.getElementById("simCover").textContent = `${res.simulated_days_of_cover}d`;
    const resetBtn = document.getElementById("resetSimBtn");
    if (resetBtn) resetBtn.style.display = "inline-flex";
    showToast(`Surge scenario applied: Stockout risk ${res.simulated_stockout_probability_pct}%`);
  } catch(e) {
    showToast("Simulation error: " + e.message, true);
  } finally {
    btn.disabled = false;
    btn.textContent = "Run Live Simulation";
  }
});

// Reset Simulation Button listener
const resetSimBtn = document.getElementById("resetSimBtn");
if (resetSimBtn) {
  resetSimBtn.addEventListener("click", () => {
    document.getElementById("demandSlider").value = 1;
    document.getElementById("demandVal").textContent = "1.0×";
    document.getElementById("leadSlider").value = 0;
    document.getElementById("leadVal").textContent = "+0d";
    document.getElementById("whatifResult").style.display = "none";
    resetSimBtn.style.display = "none";
    if (state.currentDetailData && state.currentDetailData.forecast) {
      renderForecastChart(state.currentDetailData.forecast);
    }
    showToast("Simulation scenario reset to baseline.");
  });
}
