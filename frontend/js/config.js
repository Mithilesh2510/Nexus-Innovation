// Global configuration and state store for Supply Watch
const API_BASE = window.API_BASE || "http://localhost:8000";

const state = {
  allRisk: [],
  branchesList: [],
  categoriesList: [],
  selectedRow: null,
  currentDetailData: null,
  sortState: { key: "composite_risk_score", dir: -1 },
  forecastChart: null,
  currentRecommendations: []
};
