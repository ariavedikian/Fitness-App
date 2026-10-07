/** Dashboard "Meal ideas": ask for AI suggestions that fit what's left of
 *  today's budget, and render them.
 *
 *  The server owns the budget (it computes it from goals and today's log), so
 *  the only thing sent is the meal. Every request is a billed AI call, hence
 *  the one-request-at-a-time guard below.
 */

import { apiFetch } from "./api.js";
import { defaultMeal } from "./meals.js";
import { setNotice, showRequestError } from "./notice.js";

/** One idea as a list item. Model output is untrusted text, so everything
 *  goes through textContent — never innerHTML. */
function renderSuggestion(s) {
  const item = document.createElement("li");
  item.className = "suggestion";

  const head = document.createElement("div");
  head.className = "suggestion__head";
  const name = document.createElement("span");
  name.className = "suggestion__name";
  name.textContent = s.name;
  const calories = document.createElement("span");
  calories.className = "suggestion__cal";
  calories.textContent = `~${s.calories.toLocaleString()} kcal`;
  head.append(name, calories);

  const description = document.createElement("p");
  description.className = "suggestion__desc";
  description.textContent = s.description;

  const macros = document.createElement("p");
  macros.className = "suggestion__macros";
  macros.textContent =
    `${s.protein_g} g protein · ${s.carbs_g} g carbs · ${s.fat_g} g fat`;

  item.append(head, description, macros);
  return item;
}

export function initSuggestions() {
  const card = document.querySelector("[data-suggest]");
  if (!card) return; // AI is off: the template rendered no card.

  const form = card.querySelector("[data-suggest-form]");
  const select = form.elements.meal_type;
  const button = form.querySelector('button[type="submit"]');
  const status = card.querySelector("[data-suggest-status]");
  const list = card.querySelector("[data-suggest-list]");
  const idleLabel = button.textContent.trim();
  let inFlight = false;

  select.value = defaultMeal();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    // One request at a time: each is a billed call, so a double-click or an
    // impatient re-click must not fire another.
    if (inFlight) return;
    inFlight = true;
    button.disabled = true;
    button.textContent = "Thinking…";
    list.replaceChildren();
    list.setAttribute("aria-busy", "true");
    setNotice(status, "Finding ideas that fit what's left of today…");

    try {
      const result = await apiFetch("/api/recommendations/meals", {
        method: "POST",
        body: { meal_type: select.value },
      });
      if (result.status === "budget_spent") {
        setNotice(
          status,
          "You've used today's calorie budget, so there's nothing to suggest right now.",
        );
      } else {
        setNotice(status, null);
        list.append(...result.suggestions.map(renderSuggestion));
      }
    } catch (error) {
      showRequestError(status, error);
    } finally {
      list.removeAttribute("aria-busy");
      button.textContent = idleLabel;
      button.disabled = false;
      inFlight = false;
    }
  });
}
