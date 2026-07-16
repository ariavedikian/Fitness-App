/** The "log this food" dialog, shared by the search page.
 *
 * One <dialog> element is reused for whichever food is clicked; openLogDialog
 * loads it with that food, and the form converts servings→grams and posts to
 * the log API.
 */

import { ApiError, apiFetch } from "./api.js";

let dialog;
let form;
let currentFood;
let onLoggedCallback;

/** Sensible default meal based on the time of day. */
function defaultMeal() {
  const hour = new Date().getHours();
  if (hour < 11) return "breakfast";
  if (hour < 16) return "lunch";
  if (hour < 21) return "dinner";
  return "snack";
}

/** The amount entered, converted to grams (the unit the API stores). */
function gramsFromForm() {
  const quantity = Number(form.elements.quantity.value) || 0;
  return form.elements.unit.value === "servings"
    ? quantity * currentFood.serving_size_g
    : quantity;
}

function updatePreview() {
  const factor = gramsFromForm() / 100;
  const round = (per100g) => Math.round(per100g * factor);
  dialog.querySelector("[data-preview]").textContent =
    `${round(currentFood.calories_per_100g)} kcal · ` +
    `${round(currentFood.protein_per_100g)}g P · ` +
    `${round(currentFood.carbs_per_100g)}g C · ` +
    `${round(currentFood.fat_per_100g)}g F`;
}

export function openLogDialog(food) {
  currentFood = food;
  form.reset();
  dialog.querySelector("[data-error]").hidden = true;
  dialog.querySelector("[data-food-name]").textContent = food.name;
  dialog.querySelector("[data-serving-hint]").textContent =
    `1 serving = ${food.serving_label} (${food.serving_size_g} g)`;

  form.elements.meal.value = defaultMeal();
  form.elements.unit.value = "servings";
  form.elements.quantity.value = 1;
  updatePreview();

  dialog.showModal();
}

export function initLogDialog({ onLogged } = {}) {
  dialog = document.getElementById("log-dialog");
  if (!dialog) return;
  form = dialog.querySelector("form");
  onLoggedCallback = onLogged;

  // Selects and number inputs both emit these; keeping the preview live as
  // the user changes either the amount or the unit.
  form.addEventListener("input", updatePreview);
  form.addEventListener("change", updatePreview);

  dialog
    .querySelector("[data-cancel]")
    .addEventListener("click", () => dialog.close());

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const grams = gramsFromForm();
    if (grams <= 0) return;

    const submit = form.querySelector("button[type=submit]");
    submit.disabled = true;
    try {
      await apiFetch("/api/log", {
        method: "POST",
        body: {
          food_id: currentFood.id,
          meal_type: form.elements.meal.value,
          quantity_grams: grams,
        },
      });
      dialog.close();
      onLoggedCallback?.({
        food: currentFood,
        grams,
        meal: form.elements.meal.value,
      });
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      const box = dialog.querySelector("[data-error]");
      box.textContent = error.detail;
      box.hidden = false;
    } finally {
      submit.disabled = false;
    }
  });
}
