import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import en from "./en";
import ar from "./ar";

export type Lang = "en" | "ar";
export const LANGS: Lang[] = ["en", "ar"];
const STORAGE_KEY = "pdpl.lang";

function initialLang(): Lang {
  try {
    const v = localStorage.getItem(STORAGE_KEY);
    if (v === "en" || v === "ar") return v;
  } catch {
    /* storage unavailable */
  }
  return navigator.language?.startsWith("ar") ? "ar" : "en";
}

export function applyDir(lang: Lang) {
  const el = document.documentElement;
  el.lang = lang;
  el.dir = lang === "ar" ? "rtl" : "ltr";
}

export function setLang(lang: Lang) {
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    /* ignore */
  }
  applyDir(lang);
  return i18n.changeLanguage(lang);
}

const lang = initialLang();
applyDir(lang);

i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: lang,
  fallbackLng: "en",
  interpolation: { escapeValue: false },
  returnNull: false,
});

export default i18n;

export const TZ = "Africa/Cairo";

export function locale(): string {
  return i18n.language === "ar" ? "ar-EG" : "en-GB";
}

export function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(locale(), {
    timeZone: TZ, year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  }).format(new Date(iso));
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Intl.DateTimeFormat(locale(), { timeZone: TZ, year: "numeric", month: "short", day: "numeric" }).format(
    new Date(iso),
  );
}

export function fmtNum(n: number, digits = 0): string {
  return new Intl.NumberFormat(locale(), { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(n);
}

export function fmtPct(n: number): string {
  return new Intl.NumberFormat(locale(), { style: "percent", maximumFractionDigits: 0 }).format(n);
}

/** Pick the Arabic or English variant of a bilingual catalog field. */
export function pick(obj: { en: string; ar?: string } | undefined | null): string {
  if (!obj) return "";
  return i18n.language === "ar" && obj.ar ? obj.ar : obj.en;
}
