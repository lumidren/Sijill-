import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";
import { cleanup } from "@testing-library/react";
import i18n from "../i18n";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  void i18n.changeLanguage("en");
  document.documentElement.dir = "ltr";
});

// recharts' ResponsiveContainer needs ResizeObserver
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;
