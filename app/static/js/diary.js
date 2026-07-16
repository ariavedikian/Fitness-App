/** The diary page: a day's log grouped by meal, with totals vs. goals. */

import { ApiError, apiFetch } from "./api.js";

const MEALS = [
  ["breakfast", "Breakfast"],
  ["lunch", "Lunch"],
  ["dinner", "Dinner"],
  ["snack", "Snack"],
];

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

/** Goals, or null when the user has not set up a profile yet. */
async function loadGoals() {
  try {
    return await apiFetch("/api/profile/goals");
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}

function totalRow(label, consumed, goal, unit) {
  const row = el("li", "totals__row");
  row.append(el("span", "totals__label", label));

  let text = `${consumed} ${unit}`;
  if (goal != null) {
    const diff = goal - consumed;
    const tail = diff >= 0 ? `${diff} left` : `${-diff} over`;
    text = `${consumed} / ${goal} ${unit} · ${tail}`;
  }
  row.append(el("span", "totals__value", text));
  return row;
}

function totalsPanel(totals, goals) {
  const panel = el("div", "totals card");
  panel.append(el("h2", "card__title", "Daily totals"));

  const list = el("ul", "totals__list");
  list.append(totalRow("Calories", totals.calories, goals?.calories, "kcal"));
  list.append(totalRow("Protein", totals.protein_g, goals?.macros.protein_g, "g"));
  list.append(totalRow("Carbs", totals.carbs_g, goals?.macros.carbs_g, "g"));
  list.append(totalRow("Fat", totals.fat_g, goals?.macros.fat_g, "g"));
  panel.append(list);

  if (!goals) {
    const hint = el("p", "totals__hint");
    const link = el("a", null, "Set up your profile");
    link.href = "/profile";
    hint.append(link, document.createTextNode(" to compare against goals."));
    panel.append(hint);
  }
  return panel;
}

function entryRow(entry, onDelete) {
  const row = el("div", "diary-entry");

  const info = el("div", "diary-entry__info");
  info.append(el("span", "diary-entry__name", entry.food_name));
  info.append(
    el("span", "diary-entry__amount", `${Math.round(entry.quantity_grams)} g`),
  );
  row.append(info);

  row.append(el("span", "diary-entry__cal", `${entry.nutrition.calories} kcal`));

  const remove = el("button", "diary-entry__delete", "Remove");
  remove.type = "button";
  remove.setAttribute("aria-label", `Remove ${entry.food_name}`);
  remove.addEventListener("click", () => onDelete(entry.id));
  row.append(remove);

  return row;
}

function mealSection(label, entries, onDelete) {
  const section = el("section", "meal-section");

  const header = el("div", "meal-section__header");
  header.append(el("h2", "meal-section__title", label));
  const subtotal = entries.reduce((sum, e) => sum + e.nutrition.calories, 0);
  header.append(el("span", "meal-section__subtotal", `${subtotal} kcal`));
  section.append(header);

  if (entries.length === 0) {
    section.append(el("p", "meal-section__empty", "Nothing logged."));
  } else {
    for (const entry of entries) section.append(entryRow(entry, onDelete));
  }
  return section;
}

export function initDiary() {
  const dateInput = document.getElementById("diary-date");
  const content = document.getElementById("diary-content");
  if (!dateInput || !content) return;

  dateInput.value = todayLocal();
  dateInput.max = todayLocal();

  async function render() {
    const day = dateInput.value;
    const [log, goals] = await Promise.all([
      apiFetch(`/api/log?date=${day}`),
      loadGoals(),
    ]);

    content.replaceChildren();
    content.append(totalsPanel(log.totals, goals));
    for (const [key, label] of MEALS) {
      const entries = log.entries.filter((e) => e.meal_type === key);
      content.append(mealSection(label, entries, onDelete));
    }
  }

  async function onDelete(entryId) {
    await apiFetch(`/api/log/${entryId}`, { method: "DELETE" });
    render();
  }

  dateInput.addEventListener("change", render);
  render();
}
