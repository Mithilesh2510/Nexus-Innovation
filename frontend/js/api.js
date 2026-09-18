// API Communication Layer
async function api(path, opts) {
  opts = opts || {};
  const headers = Object.assign({}, opts.headers || {});
  if (authState.token) {
    headers["Authorization"] = `Bearer ${authState.token}`;
  }
  if (opts.body && !headers["Content-Type"]) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(API_BASE + path, Object.assign({}, opts, { headers }));

  if (res.status === 401) {
    // Token missing/expired/invalid -- drop back to the login screen rather than
    // showing a confusing error, and don't let the caller act on stale data.
    clearAuth();
    if (typeof showLoginOverlay === "function") showLoginOverlay("Your session expired. Please log in again.");
    throw new Error("Session expired. Please log in again.");
  }

  if (!res.ok) {
    let err = `${path} -> ${res.status}`;
    try {
      const j = await res.json();
      if (j.detail) {
        err = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      }
    } catch(e) {}
    throw new Error(err);
  }
  return res.json();
}
