/** The profile setup/edit form: imperial in the UI, metric on the wire. */

import { ApiError, apiFetch } from "./api.js";
import { cmToFeetInches, feetInchesToCm, kgToLbs, lbsToKg } from "./units.js";

const MIN_AGE_YEARS = 13;
const MAX_AGE_YEARS = 120;

/** Return an ISO date `yearsAgo` years before today. */
function isoYearsAgo(yearsAgo) {
  const d = new Date();
  d.setFullYear(d.getFullYear() - yearsAgo);
  return d.toISOString().slice(0, 10);
}

/** Load the existing profile, if any, and fill the form with it. */
async function prefill(form) {
  try {
    const profile = await apiFetch("/api/profile");
    const { feet, inches } = cmToFeetInches(profile.height_cm);
    form.elements.feet.value = feet;
    form.elements.inches.value = inches;
    form.elements.weight_lbs.value = kgToLbs(profile.weight_kg).toFixed(1);
    form.elements.birth_date.value = profile.birth_date;
    form.elements.sex.value = profile.sex;
    form.elements.activity_level.value = profile.activity_level;
    form.elements.goal.value = profile.goal;
  } catch (error) {
    // 404 just means "no profile yet" — leave the form blank for setup.
    // Anything else is a real failure and should surface.
    if (!(error instanceof ApiError) || error.status !== 404) throw error;
  }
}

export function initProfileForm() {
  const form = document.getElementById("profile-form");
  if (!form) return;

  const errorBox = form.querySelector("[data-error]");
  const submitButton = form.querySelector("button[type=submit]");

  // Bound the date picker so the age limits are enforced before submit, the
  // same limits the server checks.
  form.elements.birth_date.max = isoYearsAgo(MIN_AGE_YEARS);
  form.elements.birth_date.min = isoYearsAgo(MAX_AGE_YEARS);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    errorBox.hidden = true;
    submitButton.disabled = true;
    submitButton.textContent = "Saving…";

    const data = new FormData(form);
    const payload = {
      // Convert to metric here so everything past this point is metric.
      height_cm: feetInchesToCm(
        Number(data.get("feet")),
        Number(data.get("inches")),
      ),
      weight_kg: lbsToKg(Number(data.get("weight_lbs"))),
      birth_date: data.get("birth_date"),
      sex: data.get("sex"),
      activity_level: data.get("activity_level"),
      goal: data.get("goal"),
    };

    try {
      await apiFetch("/api/profile", { method: "PUT", body: payload });
      // Straight to the dashboard so the freshly computed goals are the
      // first thing the user sees.
      window.location.assign("/dashboard");
    } catch (error) {
      if (!(error instanceof ApiError)) throw error;
      errorBox.textContent = error.detail;
      errorBox.hidden = false;
      submitButton.disabled = false;
      submitButton.textContent = "Save profile";
    }
  });

  prefill(form);
}
