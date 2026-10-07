/** Status-line helper shared by the AI features (meal ideas, photo estimates).
 *  Reuses the search page's notice styles: "warn" is the neutral tone,
 *  "error" the danger tone. */

import { ApiError } from "./api.js";

/** Show `message` in `el` in the given tone, or hide it when `message` is null. */
export function setNotice(el, message, tone = "warn") {
  el.hidden = message === null;
  el.textContent = message ?? "";
  el.classList.toggle("search-notice--warn", tone === "warn");
  el.classList.toggle("search-notice--error", tone === "error");
}

/** Show a failed request. The API's messages are written for people; anything
 *  else (e.g. the network dropping) gets a generic retry hint. Running out of
 *  AI requests (429) is a limit, not a failure, so it gets the neutral tone. */
export function showRequestError(el, error) {
  setNotice(
    el,
    error instanceof ApiError
      ? error.detail
      : "Couldn't reach FitTrack. Check your connection and try again.",
    error instanceof ApiError && error.status === 429 ? "warn" : "error",
  );
}
