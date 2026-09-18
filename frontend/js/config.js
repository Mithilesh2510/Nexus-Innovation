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

// Auth state -- token/role/branch for the logged-in account. Persisted to
// localStorage only so a page refresh doesn't force a re-login; it is never used
// to enforce isolation (the backend re-checks the token and branch on every
// request), only to restore the UI after a reload.
const authState = {
  token: null,
  username: null,
  role: null,       // "admin" | "branch"
  branchId: null,
  branchName: null
};

function loadStoredAuth() {
  try {
    const raw = localStorage.getItem("supplyWatchAuth");
    if (!raw) return false;
    const parsed = JSON.parse(raw);
    if (!parsed.token) return false;
    Object.assign(authState, parsed);
    return true;
  } catch (e) {
    return false;
  }
}

function persistAuth() {
  try {
    localStorage.setItem("supplyWatchAuth", JSON.stringify(authState));
  } catch (e) { /* ignore storage failures */ }
}

function clearAuth() {
  authState.token = null;
  authState.username = null;
  authState.role = null;
  authState.branchId = null;
  authState.branchName = null;
  try { localStorage.removeItem("supplyWatchAuth"); } catch (e) {}
}
