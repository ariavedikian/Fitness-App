/** Live exercise search: type a query, see matching exercises to log.
 *
 * Simpler than food search — a plain list from one local endpoint, no external
 * source and no wrapped response. The debounce + AbortController race-safety
 * mirror the food search.
 */

import { ApiError, apiFetch } from "./api.js";
import { openWorkoutDialog } from "./workout-dialog.js";

const MIN_QUERY_LENGTH = 2;
const DEBOUNCE_MS = 250;

/** createElement helper. Uses textContent, never innerHTML, to avoid XSS. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** A short label for an exercise: its muscle group, or "Cardio". */
function tagFor(exercise) {
  if (exercise.muscle_group) return exercise.muscle_group;
  return exercise.type === "cardio" ? "Cardio" : null;
}

function exerciseItem(exercise, onAdd) {
  // Reuse the food-item layout so search results look consistent app-wide.
  const item = el("li", "food-item");

  const body = el("div", "food-item__body");
  const head = el("div", "food-item__head");
  head.append(el("span", "food-item__name", exercise.name));
  const tag = tagFor(exercise);
  if (tag) head.append(el("span", "food-item__brand", tag));
  body.append(head);
  item.append(body);

  const add = el("button", "button button--primary food-item__add", "Add");
  add.type = "button";
  add.addEventListener("click", () => onAdd(exercise));
  item.append(add);

  return item;
}

export function initExerciseSearch() {
  const input = document.getElementById("exercise-search");
  const results = document.getElementById("search-results");
  const status = document.getElementById("search-status");
  if (!input || !results || !status) return;

  let timer;
  let controller;

  function showStatus(message) {
    results.replaceChildren();
    status.textContent = message;
    status.hidden = false;
  }

  function showResults(exercises) {
    status.hidden = true;
    const list = el("ul", "food-list");
    for (const exercise of exercises) {
      list.append(exerciseItem(exercise, openWorkoutDialog));
    }
    results.replaceChildren(list);
  }

  async function run(query) {
    controller = new AbortController();
    try {
      const exercises = await apiFetch(
        `/api/exercises/search?q=${encodeURIComponent(query)}`,
        { signal: controller.signal },
      );
      if (exercises.length === 0) {
        showStatus(`No exercises found for “${query}”.`);
        return;
      }
      showResults(exercises);
    } catch (error) {
      // A newer keystroke aborted this request — ignore its stale result.
      if (error.name === "AbortError") return;
      if (!(error instanceof ApiError)) throw error;
      showStatus("Something went wrong. Please try again.");
    }
  }

  input.addEventListener("input", () => {
    const query = input.value.trim();
    clearTimeout(timer);
    controller?.abort();

    if (query.length < MIN_QUERY_LENGTH) {
      showStatus(`Type at least ${MIN_QUERY_LENGTH} characters to search.`);
      return;
    }
    timer = setTimeout(() => run(query), DEBOUNCE_MS);
  });

  showStatus(`Type at least ${MIN_QUERY_LENGTH} characters to search.`);
}
