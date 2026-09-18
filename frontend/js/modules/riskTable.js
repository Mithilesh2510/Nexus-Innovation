// Medicine Supply Risk Catalog: Data loading, sorting, filtering, and table rendering
async function loadRiskTable() {
  const branch = document.getElementById("branchFilter").value;
  const crit = document.getElementById("critFilter").value;
  const cat = document.getElementById("categoryFilter").value;
  const search = document.getElementById("globalSearchInput").value.trim();

  const tbody = document.getElementById("riskTableBody");
  tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--text-dim);">Running Monte Carlo simulation models…</td></tr>`;

  try {
    let path = "/api/medicines?limit=1000";
    if (branch) path += `&branch_id=${encodeURIComponent(branch)}`;
    if (crit) path += `&criticality=${encodeURIComponent(crit)}`;
    if (cat) path += `&category=${encodeURIComponent(cat)}`;
    if (search) path += `&search=${encodeURIComponent(search)}`;

    state.allRisk = await api(path);
    renderRiskTable();
  } catch(e) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:30px; color:var(--critical);">Could not connect to API at ${API_BASE} (${e.message})</td></tr>`;
  }
}

function renderRiskTable() {
  const { key, dir } = state.sortState;
  const rows = [...state.allRisk].sort((a, b) => {
    if (typeof a[key] === "string") return a[key].localeCompare(b[key]) * dir;
    return (a[key] - b[key]) * dir;
  });

  document.getElementById("rowCount").textContent = `${rows.length} records`;
  const tbody = document.getElementById("riskTableBody");
  if (rows.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:40px; color:var(--text-dim);">No medicines match your search criteria.</td></tr>`;
    return;
  }

  tbody.innerHTML = rows.map(r => {
    const isSel = state.selectedRow && state.selectedRow.medicine_id === r.medicine_id && state.selectedRow.branch_id === r.branch_id;
    const barColor = r.stockout_probability_pct > 60 ? 'var(--critical)' : (r.stockout_probability_pct > 30 ? 'var(--high)' : 'var(--low)');
    return `
      <tr data-mid="${r.medicine_id}" data-bid="${r.branch_id}" class="${isSel ? 'selected' : ''}">
        <td>
          <div class="med-cell">
            <div class="med-name">${r.name}</div>
            <div class="med-sub">${r.medicine_id} · ${r.category}</div>
          </div>
        </td>
        <td class="num-mono" style="font-weight:600; color:var(--text-muted);">${r.branch_id}</td>
        <td><span class="risk-pill ${r.risk_tier}">${r.criticality}</span></td>
        <td>
          <div class="prob-bar-wrap">
            <span class="num-mono" style="min-width:38px;">${r.stockout_probability_pct}%</span>
            <div class="prob-bar">
              <div class="prob-fill" style="width:${Math.min(r.stockout_probability_pct, 100)}%; background:${barColor};"></div>
            </div>
          </div>
        </td>
        <td class="num-mono">${r.days_of_cover_p50}d</td>
        <td><span class="risk-pill ${r.risk_tier} num-mono">${r.composite_risk_score}</span></td>
      </tr>
    `;
  }).join("");

  tbody.querySelectorAll("tr[data-mid]").forEach(tr => {
    tr.addEventListener("click", () => selectMedicine(tr.dataset.mid, tr.dataset.bid));
  });
}

// Attach table header sort listeners
document.querySelectorAll("th[data-sort]").forEach(th => {
  th.addEventListener("click", () => {
    const key = th.dataset.sort;
    state.sortState.dir = (state.sortState.key === key) ? state.sortState.dir * -1 : -1;
    state.sortState.key = key;
    renderRiskTable();
  });
});
