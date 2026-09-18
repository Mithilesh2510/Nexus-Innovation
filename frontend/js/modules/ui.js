// UI Utilities: Toasts, status helpers, and badges
function showToast(msg, isError = false) {
  const container = document.getElementById("toastContainer");
  const el = document.createElement("div");
  el.className = `toast ${isError ? 'error' : ''}`;
  el.innerHTML = `
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="${isError ? 'M18 6L6 18M6 6l12 12' : 'M20 6L9 17l-5-5'}"/></svg>
    <span>${msg}</span>
  `;
  container.appendChild(el);
  setTimeout(() => {
    el.style.opacity = "0";
    el.style.transform = "translateX(40px)";
    el.style.transition = "all 0.3s ease";
    setTimeout(() => el.remove(), 300);
  }, 4000);
}

function riskClass(tier) {
  return tier || "Low";
}
