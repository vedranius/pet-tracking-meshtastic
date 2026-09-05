import hr from "./locales/hr.js";
import en from "./locales/en.js";

const DICTS = { hr, en };
const STORAGE_KEY = "pawtrack_locale";

function detectDefault() {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored && DICTS[stored]) return stored;
  const nav = (navigator.language || "en").toLowerCase();
  return nav.startsWith("hr") ? "hr" : "en";
}

let current = detectDefault();
const listeners = new Set();

export function getLocale() {
  return current;
}

export function setLocale(locale) {
  if (!DICTS[locale] || locale === current) return;
  current = locale;
  localStorage.setItem(STORAGE_KEY, locale);
  document.documentElement.lang = locale;
  for (const fn of listeners) fn(locale);
}

export function onLocaleChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

export function t(key, vars) {
  const dict = DICTS[current] || DICTS.en;
  let str = dict[key] ?? DICTS.en[key] ?? key;
  if (vars) {
    for (const [k, v] of Object.entries(vars)) {
      str = str.replaceAll(`{${k}}`, v);
    }
  }
  return str;
}

// Applies data-i18n / data-i18n-placeholder attributes on static HTML
// (the login screen, topbar, nav) — view modules re-render their own
// markup with t() directly instead of needing these attributes.
export function applyStaticDom() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.dataset.i18n);
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.dataset.i18nPlaceholder);
  });
  document.querySelectorAll("[data-i18n-title]").forEach((el) => {
    el.title = t(el.dataset.i18nTitle);
  });
}

document.documentElement.lang = current;
onLocaleChange(applyStaticDom);
