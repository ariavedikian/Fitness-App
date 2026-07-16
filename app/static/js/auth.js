/** Wiring for the login, register and logout controls. */

import { ApiError, apiFetch } from "./api.js";

/**
 * Submit an auth form over the API instead of as a classic form post.
 *
 * @param {object}  config
 * @param {string}  config.formId
 * @param {string}  config.endpoint
 * @param {string}  config.redirectTo   where to go once it succeeds
 * @param {string}  config.pendingLabel button text while the request is in flight
 */
export function wireAuthForm({ formId, endpoint, redirectTo, pendingLabel }) {
  const form = document.getElementById(formId);
  if (!form) return;

  const errorBox = form.querySelector("[data-error]");
  const submitButton = form.querySelector("button[type=submit]");
  const idleLabel = submitButton.textContent.trim();

  form.addEventListener("submit", async (event) => {
    // Without this the browser does its own full-page POST and the fetch
    // below never runs.
    event.preventDefault();

    errorBox.hidden = true;
    submitButton.disabled = true;
    submitButton.textContent = pendingLabel;

    try {
      // FormData reads the fields by their `name` attributes, so the payload
      // keys line up with the Pydantic schema without a manual mapping.
      const payload = Object.fromEntries(new FormData(form));
      await apiFetch(endpoint, { method: "POST", body: payload });

      // assign() rather than href = : it keeps the login page out of the
      // back-button history, so "back" from the dashboard does not land on
      // a form the user has already submitted.
      window.location.assign(redirectTo);
    } catch (error) {
      // Anything that is not an ApiError is a real bug (network, syntax) and
      // should surface in the console rather than be swallowed as "invalid
      // password".
      if (!(error instanceof ApiError)) throw error;

      errorBox.textContent = error.detail;
      errorBox.hidden = false;
      submitButton.disabled = false;
      submitButton.textContent = idleLabel;
    }
  });
}

/** Wire the header's log-out button. */
export function wireLogout() {
  const button = document.querySelector("[data-logout]");
  if (!button) return;

  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await apiFetch("/api/auth/logout", { method: "POST" });
    } finally {
      // Leave for the login page either way: if logout failed, staying on a
      // page that assumes a session is worse than starting over.
      window.location.assign("/login");
    }
  });
}
