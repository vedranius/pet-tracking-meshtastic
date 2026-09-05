import { t } from "./i18n.js";

async function request(method, path, body, rawBody) {
  const res = await fetch(path, {
    method,
    headers: rawBody ? undefined : (body !== undefined ? { "Content-Type": "application/json" } : undefined),
    // FormData bodies must NOT get an explicit Content-Type — the browser
    // sets one itself with the multipart boundary included.
    body: rawBody ? rawBody : (body !== undefined ? JSON.stringify(body) : undefined),
  });
  if (res.status === 401) {
    const err = new Error("unauthenticated");
    err.status = 401;
    throw err;
  }
  let data = null;
  const text = await res.text();
  if (text) {
    try { data = JSON.parse(text); } catch { data = text; }
  }
  if (!res.ok) {
    const detail = data && data.detail;
    // static error codes (no spaces/colons) get translated; anything with a
    // dynamic tail (e.g. "push_failed: <exception text>") is shown as-is.
    const isCode = typeof detail === "string" && /^[a-z_]+$/.test(detail);
    const message = isCode ? t(`err.${detail}`) : (detail || t("common.error_status", { status: res.status }));
    const err = new Error(message);
    err.status = res.status;
    err.detail = detail;
    throw err;
  }
  return data;
}

export const api = {
  get: (path) => request("GET", path),
  post: (path, body) => request("POST", path, body ?? {}),
  put: (path, body) => request("PUT", path, body ?? {}),
  del: (path) => request("DELETE", path),
  postFile: (path, formData) => request("POST", path, undefined, formData),
};
