/** Workouts page "Workout ideas": ask for one AI-suggested session for today,
 *  built from our exercise catalogue, and log any of its exercises through
 *  the normal workout dialog.
 *
 *  The server owns the inputs (catalogue, recent workouts, profile), so only
 *  the session length and focus are sent. Every request is a billed AI call,
 *  hence the one-request-at-a-time guard below.
 */

import { apiFetch } from "./api.js";
import { setNotice, showRequestError } from "./notice.js";
import { openWorkoutDialog } from "./workout-dialog.js";

/** createElement helper. Uses textContent, never innerHTML: the title,
 *  summary and notes are model output, which is untrusted text. */
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** "3 × 10 · Chest" or "20 min · Cardio". */
function describe(item) {
  const { exercise } = item;
  return exercise.type === "strength"
    ? [`${item.sets} × ${item.reps}`, exercise.muscle_group]
        .filter(Boolean)
        .join(" · ")
    : `${item.minutes} min · Cardio`;
}

/** One exercise of the session, with a Log button that opens the workout
 *  dialog pre-filled with the suggested numbers. */
function ideaRow(item) {
  const name = item.exercise.name;
  // Reuse the diary-entry layout, like today's list below it.
  const row = el("li", "diary-entry idea-item");

  const info = el("div", "diary-entry__info");
  info.append(el("span", "diary-entry__name", name));
  info.append(el("span", "diary-entry__amount", describe(item)));
  if (item.note) info.append(el("span", "idea-item__note", item.note));
  row.append(info);

  const done = el("span", "idea-item__done", "Logged");
  done.hidden = true;
  row.append(done);

  const log = el("button", "button button--ghost idea-item__log", "Log");
  log.type = "button";
  log.setAttribute("aria-label", `Log ${name}`);
  log.addEventListener("click", () =>
    openWorkoutDialog(item.exercise, {
      // The suggested load is never given, so weight stays the user's to add.
      prefill: {
        sets: item.sets,
        reps: item.reps,
        duration_minutes: item.minutes,
      },
      onLogged: () => {
        done.hidden = false;
        // Still a button (focus returns here when the dialog closes), so a
        // second round can be logged too.
        log.textContent = "Log again";
        log.setAttribute("aria-label", `Log ${name} again`);
      },
    }),
  );
  row.append(log);

  return row;
}

export function initWorkoutIdeas() {
  const card = document.querySelector("[data-idea]");
  if (!card) return; // AI is off: the template rendered no card.

  const form = card.querySelector("[data-idea-form]");
  const button = form.querySelector('button[type="submit"]');
  const status = card.querySelector("[data-idea-status]");
  const result = card.querySelector("[data-idea-result]");
  const title = card.querySelector("[data-idea-title]");
  const summary = card.querySelector("[data-idea-summary]");
  const list = card.querySelector("[data-idea-list]");
  const idleLabel = button.textContent.trim();
  let inFlight = false;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    // One request at a time: each is a billed call, so a double-click or an
    // impatient re-click must not fire another.
    if (inFlight) return;
    inFlight = true;
    button.disabled = true;
    button.textContent = "Thinking…";
    result.hidden = true;
    list.replaceChildren();
    result.setAttribute("aria-busy", "true");
    setNotice(status, "Putting together a session for today…");

    try {
      const idea = await apiFetch("/api/recommendations/workouts", {
        method: "POST",
        body: {
          minutes: Number(form.elements.minutes.value),
          focus: form.elements.focus.value,
        },
      });
      setNotice(status, null);
      title.textContent = idea.title;
      summary.textContent = idea.summary;
      list.append(...idea.exercises.map(ideaRow));
      result.hidden = false;
    } catch (error) {
      showRequestError(status, error);
    } finally {
      result.removeAttribute("aria-busy");
      button.textContent = idleLabel;
      button.disabled = false;
      inFlight = false;
    }
  });
}
