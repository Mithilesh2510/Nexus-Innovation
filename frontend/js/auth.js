// Auth: login form, session restore, and role-based UI restrictions.
//
// Nothing in the app fetches data until a valid token exists (see app.js's
// initApp(), only ever called from here). The UI restrictions below (hiding the
// Transfers / Stress-Tester tabs for branch accounts) are pure convenience -- the
// backend independently enforces the same restriction on every request via
// require_admin, so a branch account can't see cross-hospital data even if it
// bypassed this UI.

function showLoginOverlay(message) {
  document.getElementById("appRoot").style.display = "none";
  document.getElementById("loginOverlay").style.display = "flex";
  const errEl = document.getElementById("loginError");
  if (message) {
    errEl.textContent = message;
    errEl.style.display = "block";
  } else {
    errEl.style.display = "none";
  }
  document.getElementById("loginUsername")?.focus();
}

function hideLoginOverlay() {
  document.getElementById("loginOverlay").style.display = "none";
  document.getElementById("appRoot").style.display = "";
}

function updateUserPill() {
  const nameEl = document.getElementById("userPillName");
  const branchEl = document.getElementById("userPillBranch");
  if (!nameEl || !branchEl) return;
  nameEl.textContent = authState.username || "—";
  branchEl.textContent = authState.branchName ? ` · ${authState.branchName}` : "";
}

function applyRoleRestrictions() {
  const isAdmin = authState.role === "admin";

  // Transfers and the Macro Stress-Tester are network-wide (cross-hospital)
  // features -- the backend restricts them to admin via require_admin, so hide
  // them entirely for branch accounts rather than let every click 403.
  const restrictedTabs = ["transfers", "stress"];
  let activeTabWasRestricted = false;

  restrictedTabs.forEach(tabName => {
    const btn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    const pane = document.getElementById(`tab-${tabName}`);
    if (btn) btn.style.display = isAdmin ? "" : "none";
    if (pane && !isAdmin && pane.classList.contains("active")) {
      activeTabWasRestricted = true;
      pane.classList.remove("active");
    }
  });

  if (!isAdmin && activeTabWasRestricted) {
    const fallbackBtn = document.querySelector('.tab-btn[data-tab="procurement"]');
    const fallbackPane = document.getElementById("tab-procurement");
    document.querySelectorAll(".tab-btn").forEach(b => b.classList.remove("active"));
    fallbackBtn?.classList.add("active");
    fallbackPane?.classList.add("active");
  }

  // Facility filter: a branch account only ever gets its own branch back from
  // /api/branches (see backend/routers/dashboard.py), so lock the dropdown to
  // that single facility rather than imply a choice that doesn't exist.
  const branchFilter = document.getElementById("branchFilter");
  if (branchFilter && !isAdmin) {
    branchFilter.disabled = true;
    branchFilter.title = "Locked to your facility";
  }
}

async function handleLoginSubmit(e) {
  e.preventDefault();
  const username = document.getElementById("loginUsername").value.trim();
  const password = document.getElementById("loginPassword").value;
  const btn = document.getElementById("loginSubmitBtn");
  const errEl = document.getElementById("loginError");
  errEl.style.display = "none";

  btn.disabled = true;
  btn.textContent = "Signing in…";
  try {
    const res = await fetch(API_BASE + "/api/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.detail || "Invalid username or password");
    }

    authState.token = data.token;
    authState.username = data.username;
    authState.role = data.role;
    authState.branchId = data.branch_id;
    authState.branchName = data.branch_name;
    persistAuth();

    hideLoginOverlay();
    updateUserPill();
    applyRoleRestrictions();
    await initApp();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.style.display = "block";
  } finally {
    btn.disabled = false;
    btn.textContent = "Sign In";
  }
}

async function bootAuth() {
  document.getElementById("loginForm")?.addEventListener("submit", handleLoginSubmit);

  const userPill = document.getElementById("userPill");
  if (userPill) {
    userPill.addEventListener("click", () => {
      clearAuth();
      window.location.reload();
    });
  }

  if (!loadStoredAuth()) {
    showLoginOverlay();
    return;
  }

  // Validate the restored token against the backend (the in-memory token map
  // resets on server restart, so a stored token can be stale).
  try {
    const me = await fetch(API_BASE + "/api/me", {
      headers: { Authorization: `Bearer ${authState.token}` },
    });
    if (!me.ok) throw new Error("expired");
    const data = await me.json();
    authState.username = data.username;
    authState.role = data.role;
    authState.branchId = data.branch_id;
    authState.branchName = data.branch_name;
    persistAuth();

    hideLoginOverlay();
    updateUserPill();
    applyRoleRestrictions();
    await initApp();
  } catch (e) {
    clearAuth();
    showLoginOverlay("Your session expired. Please log in again.");
  }
}

bootAuth();
