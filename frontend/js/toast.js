export function toast(message, kind = "info") {
  const root = document.getElementById("toast-root");
  const el = document.createElement("div");
  el.className = "toast" + (kind === "error" ? " toast-err" : kind === "success" ? " toast-ok" : "");
  el.textContent = message;
  root.appendChild(el);
  setTimeout(() => el.remove(), 3200);
}
