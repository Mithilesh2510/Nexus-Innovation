// API Communication Layer
async function api(path, opts) {
  const res = await fetch(API_BASE + path, opts);
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
