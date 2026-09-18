// Advanced Forecast Fan Chart rendering using Chart.js & XGBoost Quantile Regression
let currentForecastFilter = "all";
let rawForecastData = null;

function renderForecastChart(f) {
  rawForecastData = f;
  const ctx = document.getElementById("forecastChart");
  if (!ctx) return;
  if (typeof Chart === "undefined") {
    console.warn("Chart.js is not loaded.");
    return;
  }
  if (state.forecastChart) {
    state.forecastChart.destroy();
    state.forecastChart = null;
  }

  // Update model indicator pill if present
  const modelPill = document.getElementById("chartModelPill");
  if (modelPill) {
    modelPill.textContent = f.model_type || "XGBoost Quantile Regressor";
  }

  const histDates = f.history_dates || [];
  const histVals = f.history_values || [];
  const futDates = f.dates || [];
  const p50 = f.p50 || [];
  const p10 = f.p10 || p50.map(v => Math.max(0, v * 0.7));
  const p90 = f.p90 || p50.map(v => v * 1.3);
  const p95 = f.p95 || p50.map(v => v * 1.5);

  const labels = [...histDates, ...futDates];
  const nHist = histDates.length;
  const nFut = futDates.length;

  const histPadded = [...histVals, ...Array(nFut).fill(null)];
  const p10Padded = [...Array(nHist).fill(null), ...p10];
  const p50Padded = [...Array(nHist).fill(null), ...p50];
  const p90Padded = [...Array(nHist).fill(null), ...p90];
  const p95Padded = [...Array(nHist).fill(null), ...p95];

  // Determine visibility based on active filter
  const showHist = true;
  const showCI = currentForecastFilter === "all" || currentForecastFilter === "confidence";
  const showP50 = currentForecastFilter === "all" || currentForecastFilter === "median";
  const showP95 = currentForecastFilter === "all" || currentForecastFilter === "hazard";

  state.forecastChart = new Chart(ctx, {
    type: "line",
    data: {
      labels,
      datasets: [
        // 0. Historical Actuals
        {
          label: "Historical Consumption",
          data: histPadded,
          borderColor: "#64748b",
          backgroundColor: "rgba(100, 116, 139, 0.08)",
          borderWidth: 1.8,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: "#94a3b8",
          tension: 0.15,
          hidden: !showHist,
          order: 3,
        },
        // 1. Lower Bound p10 (Anchor for CI fill)
        {
          label: "p10 Lower Bound",
          data: p10Padded,
          borderColor: "rgba(56, 189, 248, 0.2)",
          borderWidth: 1,
          borderDash: [2, 2],
          pointRadius: 0,
          tension: 0.2,
          fill: false,
          hidden: !showCI,
          order: 4,
        },
        // 2. Upper Bound p90 (Filled down to p10 for 80% CI envelope)
        {
          label: "80% Confidence Interval (p10 - p90)",
          data: p90Padded,
          borderColor: "rgba(56, 189, 248, 0.5)",
          borderWidth: 1.2,
          borderDash: [4, 4],
          pointRadius: 0,
          tension: 0.2,
          fill: 1, // fill to dataset 1 (p10)
          backgroundColor: "rgba(56, 189, 248, 0.09)",
          hidden: !showCI,
          order: 4,
        },
        // 3. Expected Median Forecast (p50)
        {
          label: "p50 Expected (XGBoost Median)",
          data: p50Padded,
          borderColor: "#38bdf8",
          backgroundColor: "rgba(56, 189, 248, 0.15)",
          borderWidth: 2.6,
          pointRadius: 0,
          pointHoverRadius: 5,
          pointHoverBackgroundColor: "#38bdf8",
          pointHoverBorderColor: "#ffffff",
          pointHoverBorderWidth: 2,
          tension: 0.22,
          hidden: !showP50,
          order: 1,
        },
        // 4. Hazard Stress Upper Bound (p95)
        {
          label: "p95 Hazard Limit (Tail Risk)",
          data: p95Padded,
          borderColor: "#f43f5e",
          borderDash: [5, 4],
          borderWidth: 1.8,
          pointRadius: 0,
          pointHoverRadius: 4,
          pointHoverBackgroundColor: "#f43f5e",
          tension: 0.2,
          hidden: !showP95,
          order: 2,
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: {
          position: "top",
          align: "end",
          labels: {
            color: "#94a3b8",
            font: { size: 10, family: "'Inter', sans-serif", weight: "500" },
            boxWidth: 12,
            boxHeight: 8,
            usePointStyle: false,
            filter: function(item) {
              // Hide the anchor p10 dataset label to keep the legend compact & clean
              return item.text !== "p10 Lower Bound";
            }
          }
        },
        tooltip: {
          backgroundColor: "rgba(15, 23, 30, 0.94)",
          titleColor: "#f0f4f8",
          titleFont: { size: 11, family: "'JetBrains Mono', monospace", weight: "700" },
          bodyColor: "#cbd5e1",
          bodyFont: { size: 11, family: "'Inter', sans-serif" },
          borderColor: "#2d3844",
          borderWidth: 1,
          padding: 10,
          boxPadding: 4,
          usePointStyle: true,
          callbacks: {
            label: function(context) {
              const val = context.parsed.y;
              if (val === null || val === undefined) return null;
              const dsLabel = context.dataset.label || "";
              if (dsLabel.includes("p10 Lower Bound")) return null;
              return ` ${dsLabel}: ${val.toFixed(1)} units`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: "#64748b",
            maxTicksLimit: 8,
            font: { size: 9.5, family: "'JetBrains Mono', monospace" }
          },
          grid: { color: "rgba(255, 255, 255, 0.03)" }
        },
        y: {
          title: {
            display: true,
            text: "Daily Units",
            color: "#475569",
            font: { size: 10, weight: "600" }
          },
          ticks: {
            color: "#64748b",
            font: { size: 9.5, family: "'JetBrains Mono', monospace" }
          },
          grid: { color: "rgba(255, 255, 255, 0.03)" }
        }
      }
    }
  });
}

// Interactive Layer Filter Buttons handler
function setupForecastFilterControls() {
  const container = document.getElementById("chartFilterPills");
  if (!container) return;

  container.querySelectorAll(".pill-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      container.querySelectorAll(".pill-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      currentForecastFilter = btn.dataset.filter;
      if (rawForecastData) {
        renderForecastChart(rawForecastData);
      }
    });
  });
}

// Auto-initialize controls on load
if (typeof document !== "undefined") {
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", setupForecastFilterControls);
  } else {
    setupForecastFilterControls();
  }
}
