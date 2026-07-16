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

function renderGoals(goals, totals) {
  setText('[data-consumed="calories"]', totals.calories.toLocaleString());
  setText('[data-goal="calories"]', goals.calories.toLocaleString());
  setText(
    '[data-remaining="calories"]',
    (goals.calories - totals.calories).toLocaleString(),
  );

  // Cap the bar at 100% even when over goal, so it never overflows its track.
  const percent = Math.min(100, Math.round((totals.calories / goals.calories) * 100));
  const bar = document.querySelector('[data-progress="calories"]');
  if (bar) bar.style.width = `${percent}%`;

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

export async function initDashboard() {
  // Today's log always loads; goals may 404 if there is no profile yet.
  const [log, goals] = await Promise.all([apiFetch("/api/log"), loadGoals()]);

  if (goals) {
    renderGoals(goals, log.totals);
  } else {
    reveal("[data-goals-empty]");
  }

  renderMeals(log.entries);
}
