/** Live food search: type a query, see matching foods with per-serving nutrition. */

import { ApiError, apiFetch } from "./api.js";
import { openLogDialog } from "./log-dialog.js";

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

function foodItem(food, onAdd) {
  const s = perServing(food);

  const item = el("li", "food-item");

  // The nutrition text sits in its own body so the Add button can sit beside
  // it, right-aligned, via the flex layout on .food-item.
  const body = el("div", "food-item__body");

  const head = el("div", "food-item__head");
  head.append(el("span", "food-item__name", food.name));
  if (food.brand) head.append(el("span", "food-item__brand", food.brand));
  // Tag external hits so it's clear which foods come from Open Food Facts (and
  // will be imported on Add) versus our own curated database.
  if (food.source === "off") {
    head.append(el("span", "food-item__source", "Open Food Facts"));
  }
  body.append(head);

  body.append(
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
  body.append(macros);
  item.append(body);

  const add = el("button", "button button--primary food-item__add", "Add");
  add.type = "button";
  add.addEventListener("click", () => onAdd(food, add));
  item.append(add);

  return item;
}

export function initFoodSearch() {
  const input = document.getElementById("food-search");
  const results = document.getElementById("search-results");
  const status = document.getElementById("search-status");
  const notice = document.getElementById("search-notice");
  if (!input || !results || !status || !notice) return;

  let timer;
  let controller;

  /** A banner that sits *beside* the results (unlike showStatus, which replaces
   *  them): used to flag a degraded external source or a failed import. Pass no
   *  text to hide it. `tone` picks the colour ("warn" or "error"). */
  function setNotice(message, tone = "warn") {
    if (!message) {
      notice.hidden = true;
      notice.className = "search-notice";
      return;
    }
    notice.textContent = message;
    notice.className = `search-notice search-notice--${tone}`;
    notice.hidden = false;
  }

  function showStatus(message) {
    results.replaceChildren();
    setNotice(null);
    status.textContent = message;
    status.hidden = false;
  }

  function showResults(hits, external) {
    status.hidden = true;
    // Only "unavailable" warrants a notice: "disabled" is a deliberate config
    // choice and "ok" needs no explanation.
    setNotice(
      external === "unavailable"
        ? "Open Food Facts is unavailable — showing your foods only."
        : null,
    );
    const list = el("ul", "food-list");
    for (const food of hits) list.append(foodItem(food, importAndLog));
    results.replaceChildren(list);
  }

  /** Handle an Add click. A local food opens the log dialog directly; an Open
   *  Food Facts hit is imported first (the server re-fetches and persists it),
   *  then the same dialog opens with the now-local food. */
  async function importAndLog(food, button) {
    if (food.source === "local") {
      openLogDialog(food);
      return;
    }

    const label = button.textContent;
    button.disabled = true;
    button.textContent = "Adding…";
    try {
      const local = await apiFetch("/api/foods/import", {
        method: "POST",
        body: { off_id: food.off_id },
      });
      openLogDialog(local);
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      setNotice(error.detail, "error");
    } finally {
      button.disabled = false;
      button.textContent = label;
    }
  }

  async function run(query) {
    controller = new AbortController();
    try {
      const { results: hits, external } = await apiFetch(
        `/api/foods/search?q=${encodeURIComponent(query)}`,
        { signal: controller.signal },
      );
      if (hits.length === 0) {
        showStatus(
          external === "unavailable"
            ? `Open Food Facts is unavailable, and no local foods match “${query}”.`
            : `No foods found for “${query}”.`,
        );
        return;
      }
      showResults(hits, external);
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
