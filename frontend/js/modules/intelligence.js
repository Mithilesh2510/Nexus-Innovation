// Intelligence Module: Supplier scorecard, macro stress testing, and anomaly sentinel validation
// Tab 3: Suppliers
async function loadSuppliers() {
  const el = document.getElementById("suppliersGrid");
  try {
    const sups = await api("/api/suppliers/intelligence");
    el.innerHTML = sups.map(s => `
      <div class="supplier-card">
        <div class="supplier-head">
          <div class="supplier-name">${s.name}</div>
          <span class="risk-pill ${s.grade_color}">${s.grade}</span>
        </div>
        <div style="font-size:11px; color:var(--text-dim); margin-bottom:10px; font-family:var(--font-mono);">${s.supplier_id} · ${s.supplied_medicines_count} SKUs Supplied</div>
        <div class="stat-grid-2" style="margin-bottom:10px;">
          <div class="mini-stat">
            <div class="k">On-Time Delivery</div>
            <div class="v num-mono" style="color:${s.on_time_delivery_pct >= 85 ? 'var(--low)' : 'var(--high)'};">${s.on_time_delivery_pct}%</div>
          </div>
          <div class="mini-stat">
            <div class="k">Mean Lead Time</div>
            <div class="v num-mono">${s.avg_lead_time_days}d ± ${s.lead_time_std_days}d</div>
          </div>
        </div>
        <div style="font-size:11.5px; color:var(--text-muted); display:flex; justify-content:space-between;">
          <span>Delayed POs: <strong style="color:var(--text);">${s.delayed_orders_count}</strong></span>
          <span>Stuck Units: <strong style="color:${s.stuck_pending_units > 0 ? 'var(--critical)' : 'var(--text)'};">${s.stuck_pending_units.toLocaleString()}</strong></span>
        </div>
      </div>
    `).join("");
  } catch(e) {
    el.innerHTML = `<div style="color:var(--critical); padding:20px;">Failed to load suppliers: ${e.message}</div>`;
  }
}

// Tab 4: Macro Stress Tester
async function runPresetStress(name, demandMultiplier, extraLead) {
  try {
    showToast(`Running systemic stress test: ${name}…`);
    const res = await api("/api/simulate/network", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        scenario_name: name,
        demand_multiplier: demandMultiplier,
        lead_time_extra_days: extraLead
      })
    });

    const sum = res.impact_summary;
    document.getElementById("stressResultContainer").style.display = "block";
    document.getElementById("stressScenarioTitle").textContent = `Stress Impact Analysis: ${name} (${demandMultiplier}× Demand, +${extraLead}d Delay)`;
    document.getElementById("stressCritVal").textContent = sum.critical_skus_after;
    document.getElementById("stressCritDelta").textContent = `+${sum.critical_delta} jump from baseline`;
    document.getElementById("stressHighVal").textContent = sum.high_skus_after;
    document.getElementById("stressHighDelta").textContent = `Baseline was ${sum.high_skus_before}`;
    document.getElementById("stressStockoutVal").textContent = sum.avg_stockout_pct_after + "%";
    document.getElementById("stressStockoutDelta").textContent = `+${sum.stockout_delta_pct}% stockout surge`;

    document.getElementById("stressVulnerableTable").innerHTML = `
      <table>
        <thead>
          <tr><th>Medicine</th><th>Branch</th><th>Criticality</th><th>Stressed Risk Score</th><th>Stressed Stockout %</th></tr>
        </thead>
        <tbody>
          ${res.top_vulnerable_skus.slice(0, 8).map(s => `
            <tr>
              <td><span style="font-weight:600;">${s.name}</span></td>
              <td class="num-mono">${s.branch_id}</td>
              <td><span class="risk-pill Critical">${s.criticality}</span></td>
              <td class="num-mono" style="color:var(--critical); font-weight:700;">${s.composite_risk_score}</td>
              <td class="num-mono" style="color:var(--critical);">${s.stockout_probability_pct}%</td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch(e) {
    showToast("Stress test failed: " + e.message, true);
  }
}

// Tab 5: Anomaly Sentinel Validation
async function loadValidation() {
  const el = document.getElementById("validationContent");
  try {
    const res = await api("/api/anomalies/validate");
    el.innerHTML = `
      <div class="kpi-row" style="margin-bottom:20px; grid-template-columns:repeat(3, 1fr);">
        <div class="kpi-card safe">
          <div class="kpi-label">Detector Overall Recall</div>
          <div class="kpi-value">${(res.overall_recall * 100).toFixed(1)}%</div>
          <div class="kpi-sub">Within ±1 day tolerance</div>
        </div>
        <div class="kpi-card">
          <div class="kpi-label">Total Ground-Truth Events</div>
          <div class="kpi-value">${res.total_labeled_anomalies}</div>
          <div class="kpi-sub">From usage_anomalies.csv</div>
        </div>
        <div class="kpi-card cyan">
          <div class="kpi-label">Successfully Detected</div>
          <div class="kpi-value">${res.total_caught}</div>
          <div class="kpi-sub">Caught drift &amp; outbreaks</div>
        </div>
      </div>
      <div style="font-weight:600; font-size:12.5px; margin-bottom:8px;">Recall Evaluation by Medicine Series:</div>
      <table>
        <thead>
          <tr><th>Medicine ID</th><th>Branch</th><th>Ground Truth Events</th><th>Detected</th><th>Series Recall</th></tr>
        </thead>
        <tbody>
          ${res.per_medicine.map(m => `
            <tr>
              <td class="num-mono" style="color:var(--cyan); font-weight:600;">${m.medicine_id}</td>
              <td class="num-mono">${m.branch_id}</td>
              <td class="num-mono">${m.truth_count}</td>
              <td class="num-mono">${m.caught}</td>
              <td>
                <div class="prob-bar-wrap">
                  <span class="num-mono" style="min-width:35px;">${(m.recall * 100).toFixed(0)}%</span>
                  <div class="prob-bar"><div class="prob-fill" style="width:${m.recall * 100}%; background:var(--low);"></div></div>
                </div>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    `;
  } catch(e) {
    el.innerHTML = `<div style="color:var(--critical); padding:20px;">Failed to load validation: ${e.message}</div>`;
  }
}
