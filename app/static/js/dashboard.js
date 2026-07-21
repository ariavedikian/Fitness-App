/** Dashboard: today's consumed nutrition against the profile's goals. */

import { ApiError, apiFetch } from "./api.js";
import { renderSparkline } from "./chart.js";
import { kgToLbs } from "./units.js";

function setText(selector, value) {
  const el = document.querySelector(selector);
  if (el) el.textContent = value;
}

function reveal(selector) {
  document.querySelectorAll(selector).forEach((el) => {
    el.hidden = false;
  });
}

/** Goals, or null when the user has not set up a profile yet. */
async function loadGoals() {
  try {
    return await apiFetch("/api/profile/goals");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

function renderGoals(goals, totals, burned) {
  // Net calories = eaten − burned. Exercise adds its calories back to the
  // day's budget, so remaining = goal − eaten + burned (the MyFitnessPal
  // model). Macros are untouched: exercise burns calories, not protein.
  const net = totals.calories - burned;

  setText('[data-consumed="calories"]', totals.calories.toLocaleString());
  setText('[data-goal="calories"]', goals.calories.toLocaleString());
  setText('[data-remaining="calories"]', (goals.calories - net).toLocaleString());

  // Bar tracks net vs goal; clamp to 0–100 so a big burn or an over-goal day
  // never sends it outside its track.
  const percent = Math.max(0, Math.min(100, Math.round((net / goals.calories) * 100)));
  const bar = document.querySelector('[data-progress="calories"]');
  if (bar) bar.style.width = `${percent}%`;

  // The "from exercise" line only makes sense once something was burned.
  const exercise = document.querySelector('[data-exercise="calories"]');
  if (exercise) {
    if (burned > 0) {
      setText('[data-burned="calories"]', burned.toLocaleString());
      exercise.hidden = false;
    } else {
      exercise.hidden = true;
    }
  }

  for (const macro of ["protein", "carbs", "fat"]) {
    setText(`[data-consumed="${macro}"]`, totals[`${macro}_g`]);
    setText(`[data-goal="${macro}"]`, goals.macros[`${macro}_g`]);
  }

  reveal("[data-goals-ready]");
}

function renderMeals(entries) {
  if (entries.length === 0) {
    reveal("[data-log-empty]");
    return;
  }

  const list = document.querySelector("[data-log-list]");
  list.replaceChildren();
  for (const entry of entries) {
    const item = document.createElement("li");
    item.className = "mini-list__item";

    const name = document.createElement("span");
    name.textContent = entry.food_name;

    const calories = document.createElement("span");
    calories.className = "mini-list__cal";
    calories.textContent = `${entry.nutrition.calories} kcal`;

    item.append(name, calories);
    list.append(item);
  }

  reveal("[data-log-ready]");
}

function renderWorkouts(entries) {
  if (entries.length === 0) {
    reveal("[data-workouts-empty]");
    return;
  }

  const list = document.querySelector("[data-workouts-list]");
  list.replaceChildren();
  for (const entry of entries) {
    const item = document.createElement("li");
    item.className = "mini-list__item";

    const name = document.createElement("span");
    name.textContent = entry.exercise_name;

    const calories = document.createElement("span");
    calories.className = "mini-list__cal";
    calories.textContent =
      entry.calories_burned != null ? `${entry.calories_burned} kcal` : "—";

    item.append(name, calories);
    list.append(item);
  }

  reveal("[data-workouts-ready]");
}

/** Current weight (the latest weigh-in) and the change from the one before it.
 *  Weight is shown in pounds to match the rest of the UI; the series comes back
 *  oldest-first, so the newest entry is last. */
function renderWeight(entries) {
  if (entries.length === 0) {
    reveal("[data-weight-empty]");
    return;
  }

  const latest = entries[entries.length - 1];
  setText("[data-weight-current]", kgToLbs(latest.weight_kg).toFixed(1));

  // A small trend of the recent weigh-ins (cap the history so the shape stays
  // legible in a card-sized sparkline).
  const spark = document.querySelector("[data-weight-spark]");
  if (spark) {
    renderSparkline(
      spark,
      entries.slice(-12).map((e) => kgToLbs(e.weight_kg)),
    );
  }

  if (entries.length >= 2) {
    const prev = entries[entries.length - 2];
    const delta =
      Math.round((kgToLbs(latest.weight_kg) - kgToLbs(prev.weight_kg)) * 10) / 10;
    const changeEl = document.querySelector("[data-weight-change]");
    if (changeEl && delta !== 0) {
      // U+2212 minus for a loss; neutral tone, no good/bad colour.
      const sign = delta > 0 ? "+" : "−";
      changeEl.textContent = `${sign}${Math.abs(delta).toFixed(1)} lb since last weigh-in`;
      changeEl.hidden = false;
    }
  }

  reveal("[data-weight-ready]");
}

export async function initDashboard() {
  // Today's log, workouts and weight history always load; goals may 404 if
  // there is no profile yet.
  const [log, workouts, weight, goals] = await Promise.all([
    apiFetch("/api/log"),
    apiFetch("/api/workouts"),
    apiFetch("/api/weight"),
    loadGoals(),
  ]);

  if (goals) {
    renderGoals(goals, log.totals, workouts.total_calories_burned);
  } else {
    reveal("[data-goals-empty]");
  }

  renderMeals(log.entries);
  renderWorkouts(workouts.entries);
  renderWeight(weight.entries);
}
