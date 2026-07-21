/** Dashboard: today's consumed nutrition against the profile's goals. */

import { ApiError, apiFetch } from "./api.js";

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

export async function initDashboard() {
  // Today's log and workouts always load; goals may 404 if there is no
  // profile yet.
  const [log, workouts, goals] = await Promise.all([
    apiFetch("/api/log"),
    apiFetch("/api/workouts"),
    loadGoals(),
  ]);

  if (goals) {
    renderGoals(goals, log.totals, workouts.total_calories_burned);
  } else {
    reveal("[data-goals-empty]");
  }

  renderMeals(log.entries);
  renderWorkouts(workouts.entries);
}
