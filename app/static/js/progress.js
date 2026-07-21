/** The progress page: log a weigh-in (imperial UI, metric on the wire) and show
 *  weight history with the change from each previous weigh-in.
 *
 *  Weight is entered and shown in pounds to match the profile form; the API
 *  stores kilograms, so we convert on the way in and out. Per-entry deltas are
 *  computed here from the ordered series — the server returns pure facts. */

import { ApiError, apiFetch } from "./api.js";
import { kgToLbs, lbsToKg } from "./units.js";

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** Today's date as YYYY-MM-DD in the user's own timezone (not UTC). */
function todayLocal() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** "2026-07-20" → "Jul 20, 2026", parsed as a local date so the day never
 *  shifts by a timezone (new Date("2026-07-20") would be UTC midnight). */
function formatDate(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric",
  });
}

const lbs = (kg) => kgToLbs(kg).toFixed(1);

/** The change from the previous weigh-in, in pounds, as neutral signed text.
 *  No colour or good/bad framing — direction of weight change isn't inherently
 *  either, and depends on the user's goal. */
function changeText(entry, prev) {
  if (!prev) return "First weigh-in";
  const delta = Math.round((kgToLbs(entry.weight_kg) - kgToLbs(prev.weight_kg)) * 10) / 10;
  if (delta === 0) return "No change";
  // U+2212 minus sign for a losing entry; it reads better than a hyphen.
  const sign = delta > 0 ? "+" : "−";
  return `${sign}${Math.abs(delta).toFixed(1)} lb since ${formatDate(prev.date)}`;
}

function historyRow(entry, prev, onDelete) {
  // Reuse the diary-entry layout for a consistent logged-item look.
  const row = el("div", "diary-entry");

  const info = el("div", "diary-entry__info");
  info.append(el("span", "diary-entry__name", formatDate(entry.date)));
  info.append(el("span", "diary-entry__amount", changeText(entry, prev)));
  row.append(info);

  row.append(el("span", "diary-entry__cal", `${lbs(entry.weight_kg)} lb`));

  const remove = el("button", "diary-entry__delete", "Remove");
  remove.type = "button";
  remove.setAttribute("aria-label", `Remove weigh-in from ${formatDate(entry.date)}`);
  remove.addEventListener("click", () => onDelete(entry.id));
  row.append(remove);

  return row;
}

/** Pre-fill the weight box with the profile's current weight, for a one-tap
 *  "same as last time". No profile yet just leaves it blank. */
async function prefillWeight(form) {
  try {
    const profile = await apiFetch("/api/profile");
    form.elements.weight_lbs.value = lbs(profile.weight_kg);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
  }
}

export function initProgress() {
  const form = document.getElementById("weight-form");
  const container = document.getElementById("weight-history");
  const summaryEl = document.getElementById("history-summary");
  const status = document.getElementById("weight-status");
  if (!form || !container) return;

  const errorBox = form.querySelector("[data-error]");
  const submitButton = form.querySelector("button[type=submit]");

  // Default to today, and stop the picker offering future dates.
  form.elements.date.value = todayLocal();
  form.elements.date.max = todayLocal();

  async function onDelete(id) {
    await apiFetch(`/api/weight/${id}`, { method: "DELETE" });
    await refresh();
  }

  async function refresh() {
    const { entries } = await apiFetch("/api/weight");

    if (entries.length === 0) {
      summaryEl.textContent = "";
      container.replaceChildren(
        el("p", "today__empty", "No weigh-ins yet. Add your first above."),
      );
      return;
    }

    summaryEl.textContent =
      entries.length === 1 ? "1 weigh-in" : `${entries.length} weigh-ins`;

    // entries are oldest-first: each row's change compares to the one before
    // it. Build in that order, then reverse so newest shows on top.
    const rows = entries.map((entry, i) =>
      historyRow(entry, i > 0 ? entries[i - 1] : null, onDelete),
    );
    rows.reverse();

    const list = el("div", "workout-list");
    list.append(...rows);
    container.replaceChildren(list);
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.hidden = true;
    status.hidden = true;
    submitButton.disabled = true;
    submitButton.textContent = "Saving…";

    const data = new FormData(form);
    const payload = {
      // An empty date means "today"; the server defaults it too.
      date: data.get("date") || undefined,
      // Convert to metric here so everything past this point is metric.
      weight_kg: lbsToKg(Number(data.get("weight_lbs"))),
    };

    try {
      await apiFetch("/api/weight", { method: "POST", body: payload });
      status.textContent = "Weigh-in saved.";
      status.hidden = false;
      await refresh();
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      errorBox.textContent = error.detail;
      errorBox.hidden = false;
    } finally {
      submitButton.disabled = false;
      submitButton.textContent = "Save weigh-in";
    }
  });

  prefillWeight(form);
  refresh();
}
