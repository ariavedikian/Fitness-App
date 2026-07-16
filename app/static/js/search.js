/** Live food search: type a query, see matching foods with per-serving nutrition. */

import { ApiError, apiFetch } from "./api.js";

// Below this length, searching is noise ("a" would match half the database).
const MIN_QUERY_LENGTH = 2;
// Wait this long after the last keystroke before querying, so a fast typist
// triggers one request instead of one per letter.
const DEBOUNCE_MS = 250;

/** Derive per-serving nutrition from the canonical per-100 g values. */
function perServing(food) {
  const factor = food.serving_size_g / 100;
  return {
    calories: Math.round(food.calories_per_100g * factor),
    protein: Math.round(food.protein_per_100g * factor),
    carbs: Math.round(food.carbs_per_100g * factor),
    fat: Math.round(food.fat_per_100g * factor),
  };
}

/** Small createElement helper. Uses textContent, never innerHTML, so a food
 *  name can never inject markup — important once names come from external
 *  APIs in a later milestone. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function foodItem(food) {
  const s = perServing(food);

  const item = el("li", "food-item");

  const head = el("div", "food-item__head");
  head.append(el("span", "food-item__name", food.name));
  if (food.brand) head.append(el("span", "food-item__brand", food.brand));
  item.append(head);

  item.append(
    el(
      "p",
      "food-item__serving",
      `Per ${food.serving_label} (${food.serving_size_g} g)`,
    ),
  );

  const macros = el("p", "food-item__macros");
  macros.append(el("strong", null, `${s.calories} kcal`));
  macros.append(
    document.createTextNode(
      ` · ${s.protein}g protein · ${s.carbs}g carbs · ${s.fat}g fat`,
    ),
  );
  item.append(macros);

  return item;
}

export function initFoodSearch() {
  const input = document.getElementById("food-search");
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

  function showResults(foods) {
    status.hidden = true;
    const list = el("ul", "food-list");
    for (const food of foods) list.append(foodItem(food));
    results.replaceChildren(list);
  }

  async function run(query) {
    controller = new AbortController();
    try {
      const foods = await apiFetch(
        `/api/foods/search?q=${encodeURIComponent(query)}`,
        { signal: controller.signal },
      );
      if (foods.length === 0) {
        showStatus(`No foods found for “${query}”.`);
        return;
      }
      showResults(foods);
    } catch (error) {
      // A newer keystroke aborted this request — its results are stale, so
      // ignore it and let the newer one win.
      if (error.name === "AbortError") return;
      if (!(error instanceof ApiError)) throw error;
      showStatus("Something went wrong. Please try again.");
    }
  }

  input.addEventListener("input", () => {
    const query = input.value.trim();
    clearTimeout(timer);
    // Cancel any request still in flight so a slow earlier query can never
    // overwrite the results of a later one (a fetch race).
    controller?.abort();

    if (query.length < MIN_QUERY_LENGTH) {
      showStatus(`Type at least ${MIN_QUERY_LENGTH} characters to search.`);
      return;
    }
    timer = setTimeout(() => run(query), DEBOUNCE_MS);
  });

  showStatus(`Type at least ${MIN_QUERY_LENGTH} characters to search.`);
}
