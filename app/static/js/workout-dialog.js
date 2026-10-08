/** The "log this exercise" dialog, shared by the workouts page.
 *
 * One <dialog> is reused for whichever exercise's Add button is clicked. Which
 * field group shows — strength (sets/reps/weight) or cardio (duration/distance/
 * calories) — depends on the exercise's type. Only the visible group's key
 * fields are marked required, since a hidden required input would block submit.
 *
 * A workout idea opens it pre-filled with the suggested numbers, which the
 * user adjusts to what they actually did — nothing is logged unreviewed.
 */

import { ApiError, apiFetch } from "./api.js";

let dialog;
let form;
let strengthFields;
let cardioFields;
let currentExercise;
let currentOnLogged;
let onLoggedCallback;

/** A positive number from a field, or undefined when blank/zero. */
function optionalNumber(value) {
  const n = Number(value);
  return value !== "" && Number.isFinite(n) && n > 0 ? n : undefined;
}

/** Build the POST body from the visible field group. */
function buildPayload() {
  const payload = { exercise_id: currentExercise.id };

  if (currentExercise.type === "strength") {
    payload.sets = optionalNumber(form.elements.sets.value);
    payload.reps = optionalNumber(form.elements.reps.value);
    const weight = optionalNumber(form.elements.weight_kg.value);
    if (weight !== undefined) payload.weight_kg = weight;
  } else {
    payload.duration_minutes = optionalNumber(form.elements.duration_minutes.value);
    const distance = optionalNumber(form.elements.distance_km.value);
    const calories = optionalNumber(form.elements.calories_burned.value);
    if (distance !== undefined) payload.distance_km = distance;
    if (calories !== undefined) payload.calories_burned = calories;
  }

  return payload;
}

/** Open the dialog for `exercise`.
 *
 * `prefill` maps field names to starting values (e.g. a workout idea's
 * `{ sets, reps }` or `{ duration_minutes }`); null values are skipped.
 * `onLogged` runs after the page-wide callback, and only if this exercise is
 * actually logged — cancelling never calls it. */
export function openWorkoutDialog(exercise, { prefill = {}, onLogged } = {}) {
  currentExercise = exercise;
  currentOnLogged = onLogged;
  form.reset();
  dialog.querySelector("[data-error]").hidden = true;
  dialog.querySelector("[data-exercise-name]").textContent = exercise.name;

  const isStrength = exercise.type === "strength";
  const prefilled = Object.entries(prefill).filter(([, value]) => value != null);
  for (const [name, value] of prefilled) form.elements[name].value = value;

  dialog.querySelector("[data-type-hint]").textContent =
    prefilled.length > 0
      ? "Filled in from your workout idea — change it to what you actually did."
      : isStrength
        ? "Strength — enter your sets and reps."
        : "Cardio — enter how long you went for.";

  strengthFields.hidden = !isStrength;
  cardioFields.hidden = isStrength;

  // Required only on the visible group; a hidden required input can't be
  // focused and would silently block the form from submitting.
  form.elements.sets.required = isStrength;
  form.elements.reps.required = isStrength;
  form.elements.duration_minutes.required = !isStrength;

  dialog.showModal();
}

export function initWorkoutDialog({ onLogged } = {}) {
  dialog = document.getElementById("workout-dialog");
  if (!dialog) return;
  form = dialog.querySelector("form");
  strengthFields = dialog.querySelector('[data-fields="strength"]');
  cardioFields = dialog.querySelector('[data-fields="cardio"]');
  onLoggedCallback = onLogged;

  dialog
    .querySelector("[data-cancel]")
    .addEventListener("click", () => dialog.close());

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const submit = form.querySelector("button[type=submit]");
    submit.disabled = true;
    try {
      const entry = await apiFetch("/api/workouts", {
        method: "POST",
        body: buildPayload(),
      });
      dialog.close();
      onLoggedCallback?.(entry);
      currentOnLogged?.(entry);
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
