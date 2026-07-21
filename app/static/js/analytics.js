/** The analytics page: calorie and macro trends over a selectable window,
 *  drawn with the shared SVG chart module. */

import { apiFetch } from "./api.js";
import { renderLineChart } from "./chart.js";

// Fixed order → fixed colour, matching the validated categorical tokens. Never
// reorder: colour follows the macro, not its rank on any given day.
const MACRO_SERIES = [
  { key: "protein_g", label: "Protein", color: "var(--chart-series-1)" },
  { key: "carbs_g", label: "Carbs", color: "var(--chart-series-2)" },
  { key: "fat_g", label: "Fat", color: "var(--chart-series-3)" },
];

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** "2026-07-20" → local-midnight timestamp, for the time axis. */
function dateToTs(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).getTime();
}

function formatDateShort(ts) {
  return new Date(ts).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function fullDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

function showHint(container, text) {
  container.replaceChildren(el("p", "chart__empty", text));
}

function renderCharts(entries) {
  const calContainer = document.getElementById("calorie-chart");
  const macroContainer = document.getElementById("macro-chart");
  if (!calContainer || !macroContainer) return;

  // A trend needs at least two days to connect.
  if (entries.length < 2) {
    const hint = "Log meals on at least two days to see your trends.";
    showHint(calContainer, hint);
    showHint(macroContainer, hint);
    return;
  }

  const xs = entries.map((e) => dateToTs(e.date));
  const span = `${fullDate(entries[0].date)} to ${fullDate(entries.at(-1).date)}`;

  renderLineChart(calContainer, {
    series: [
      {
        points: entries.map((e, i) => ({ x: xs[i], y: e.calories })),
        color: "var(--color-accent)",
      },
    ],
    formatX: formatDateShort,
    formatY: (v) => v.toLocaleString(),
    formatValue: (v) => `${v.toLocaleString()} kcal`,
    ariaLabel: `Daily calories eaten, ${span}.`,
  });

  renderLineChart(macroContainer, {
    series: MACRO_SERIES.map((m) => ({
      points: entries.map((e, i) => ({ x: xs[i], y: e[m.key] })),
      color: m.color,
      label: m.label,
    })),
    formatX: formatDateShort,
    formatY: (v) => `${v}`,
    formatValue: (v) => `${v} g`,
    ariaLabel: `Daily protein, carbs, and fat in grams, ${span}.`,
  });
}

export function initAnalytics() {
  const rangeSelect = document.getElementById("range-select");
  if (!rangeSelect) return;

  async function load() {
    const { entries } = await apiFetch(
      `/api/analytics/daily?days=${rangeSelect.value}`,
    );
    renderCharts(entries);
  }

  rangeSelect.addEventListener("change", load);
  load();
}
