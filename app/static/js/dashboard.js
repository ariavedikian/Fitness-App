/** Fills the dashboard's goal cards from /api/profile/goals. */

import { ApiError, apiFetch } from "./api.js";

function setGoal(name, value) {
  const el = document.querySelector(`[data-goal="${name}"]`);
  if (el) el.textContent = value;
}

function reveal(selector) {
  document.querySelectorAll(selector).forEach((el) => {
    el.hidden = false;
  });
}

export async function initDashboard() {
  let goals;
  try {
    goals = await apiFetch("/api/profile/goals");
  } catch (error) {
    // No profile yet: show each card's call-to-action instead of numbers.
    if (error instanceof ApiError && error.status === 404) {
      reveal("[data-goals-empty]");
      return;
    }
    throw error;
  }

  // toLocaleString() adds the thousands separator (2,759 rather than 2759).
  setGoal("calories", goals.calories.toLocaleString());
  setGoal("tdee", goals.tdee.toLocaleString());
  setGoal("protein", goals.macros.protein_g);
  setGoal("carbs", goals.macros.carbs_g);
  setGoal("fat", goals.macros.fat_g);

  reveal("[data-goals-ready]");
}
