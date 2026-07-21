/** The workouts page's "today" list: what you've logged today, with a running
 *  calories-burned total and per-entry delete. Exposes refresh() so the log
 *  dialog can re-render the list after a new entry lands. */

import { apiFetch } from "./api.js";

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

/** A human summary of an entry's metrics, per its type. */
function metricsSummary(entry) {
  if (entry.type === "strength") {
    let text = `${entry.sets} × ${entry.reps}`;
    if (entry.weight_kg != null) text += ` @ ${entry.weight_kg} kg`;
    return text;
  }
  const parts = [`${entry.duration_minutes} min`];
  if (entry.distance_km != null) parts.push(`${entry.distance_km} km`);
  return parts.join(" · ");
}

function workoutRow(entry, onDelete) {
  // Reuse the diary-entry layout for a consistent logged-item look.
  const row = el("div", "diary-entry");

  const info = el("div", "diary-entry__info");
  info.append(el("span", "diary-entry__name", entry.exercise_name));
  info.append(el("span", "diary-entry__amount", metricsSummary(entry)));
  row.append(info);

  const calories =
    entry.calories_burned != null ? `${entry.calories_burned} kcal` : "—";
  row.append(el("span", "diary-entry__cal", calories));

  const remove = el("button", "diary-entry__delete", "Remove");
  remove.type = "button";
  remove.setAttribute("aria-label", `Remove ${entry.exercise_name}`);
  remove.addEventListener("click", () => onDelete(entry.id));
  row.append(remove);

  return row;
}

export function initTodayWorkouts() {
  const container = document.getElementById("today-workouts");
  const totalEl = document.getElementById("today-total");
  if (!container) return { refresh: () => {} };

  async function onDelete(id) {
    await apiFetch(`/api/workouts/${id}`, { method: "DELETE" });
    refresh();
  }

  async function refresh() {
    const data = await apiFetch(`/api/workouts?date=${todayLocal()}`);

    totalEl.textContent =
      data.total_calories_burned > 0
        ? `${data.total_calories_burned} kcal burned`
        : "";

    if (data.entries.length === 0) {
      container.replaceChildren(
        el("p", "today__empty", "No workouts logged yet today."),
      );
      return;
    }

    const list = el("div", "workout-list");
    for (const entry of data.entries) list.append(workoutRow(entry, onDelete));
    container.replaceChildren(list);
  }

  refresh();
  return { refresh };
}
