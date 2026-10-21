import { describe, expect, it } from "vitest";
import { formatPct, summarize, type ProberMinute } from "./admin-prober";

function minute(index: number, success: number, expected = 12): ProberMinute {
  return {
    minute: new Date(Date.UTC(2026, 9, 21, 10, index)).toISOString(),
    success_count: success,
    expected_count: expected,
    success_pct: Math.min(100, (100 * success) / expected),
  };
}

describe("summarize", () => {
  it("calcule le taux de la fenêtre sur les sommes, pas sur la moyenne des pourcentages", () => {
    // 13 + 11 = 24 réussites pour 24 attendues : 100 %, alors que la moyenne des
    // pourcentages plafonnés donnerait (100 + 91,7) / 2 = 95,8 %.
    const summary = summarize([minute(0, 13), minute(1, 11)]);
    expect(summary.windowPct).toBe(100);
  });

  it("donne la dernière minute complète et compte les minutes sans réussite", () => {
    const points = [minute(0, 12), minute(1, 0), minute(2, 0), minute(3, 6)];
    const summary = summarize(points);
    expect(summary.last).toBe(points[3]);
    expect(summary.minutesWithoutSuccess).toBe(2);
    expect(summary.windowPct).toBe(37.5);
  });

  it("reste défini sans aucun point", () => {
    expect(summarize([])).toEqual({ windowPct: 0, last: null, minutesWithoutSuccess: 0 });
  });
});

describe("formatPct", () => {
  it("formate à la française, une décimale au plus", () => {
    expect(formatPct(99.6)).toMatch(/^99,6\s%$/);
    expect(formatPct(100)).toMatch(/^100\s%$/);
  });
});
