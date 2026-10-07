/** Foods page "Estimate from a photo".
 *
 *  1. Downscale the chosen photo in the browser and re-encode it as JPEG.
 *  2. Upload it for an AI estimate: items with an estimated weight and
 *     nutrition per 100 g.
 *  3. Let the user review it — correct the grams (every figure rescales),
 *     remove items, pick the meal — and only then log it.
 *
 *  Nothing is logged without that review, and the photo itself is never
 *  stored: it exists only for the length of the estimate request.
 */

import { ApiError, apiFetch } from "./api.js";
import { defaultMeal } from "./meals.js";
import { setNotice, showRequestError } from "./notice.js";

// Opus 4.8 reads images up to 2576 px, but ~1568 px is plenty to identify
// food and judge portions — about a third of the image tokens, and a phone
// upload of a few hundred KB instead of several MB.
const MAX_EDGE_PX = 1568;
const JPEG_QUALITY = 0.85;

/** Decode, downscale and re-encode a photo as JPEG. Re-encoding through a
 *  canvas also drops the original's metadata (including GPS location) and
 *  converts formats Claude can't read (e.g. HEIC, where the browser can decode
 *  it). Rejects if the browser can't decode the file at all. */
async function downscaleToJpeg(file) {
  // "from-image" applies the camera's orientation tag, so a portrait phone
  // photo isn't sent sideways once the metadata is gone.
  const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
  const scale = Math.min(1, MAX_EDGE_PX / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);

  const ctx = canvas.getContext("2d");
  // JPEG has no transparency: without a backdrop, a transparent PNG's clear
  // pixels would encode as black.
  ctx.fillStyle = "#fff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();

  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => (blob ? resolve(blob) : reject(new Error("JPEG encoding failed"))),
      "image/jpeg",
      JPEG_QUALITY,
    );
  });
}

/** Nutrition for an item at its current grams — unrounded, so totals can sum
 *  first and round once. */
function nutritionOf(item) {
  const factor = item.grams / 100;
  return {
    calories: item.calories_per_100g * factor,
    protein: item.protein_per_100g * factor,
    carbs: item.carbs_per_100g * factor,
    fat: item.fat_per_100g * factor,
  };
}

function formatNutrition(n) {
  const r = Math.round;
  return `${r(n.calories)} kcal · ${r(n.protein)} g P · ${r(n.carbs)} g C · ${r(n.fat)} g F`;
}

const CONFIDENCE_LABELS = {
  low: "Low confidence",
  medium: "Medium confidence",
  high: "High confidence",
};

export function initPhotoEstimate({ onLogged } = {}) {
  const entry = document.querySelector("[data-photo]");
  if (!entry) return; // AI is off: the template rendered no photo control.

  const button = entry.querySelector("[data-photo-button]");
  const input = entry.querySelector("[data-photo-input]");
  const status = entry.querySelector("[data-photo-status]");
  const idleLabel = button.textContent.trim();

  const dialog = document.getElementById("photo-dialog");
  const form = dialog.querySelector("form");
  const list = dialog.querySelector("[data-photo-items]");
  const total = dialog.querySelector("[data-photo-total]");
  const submit = dialog.querySelector('button[type="submit"]');
  const errorBox = dialog.querySelector("[data-error]");

  // The items under review; grams change as the user edits them.
  let items = [];
  let busy = false;

  function updateTotals() {
    const sum = items
      .map(nutritionOf)
      .reduce(
        (a, n) => ({
          calories: a.calories + n.calories,
          protein: a.protein + n.protein,
          carbs: a.carbs + n.carbs,
          fat: a.fat + n.fat,
        }),
        { calories: 0, protein: 0, carbs: 0, fat: 0 },
      );
    total.textContent = `Total: ${formatNutrition(sum)}`;
    submit.textContent =
      items.length === 1 ? "Log 1 item" : `Log ${items.length} items`;
    submit.disabled = items.length === 0;
  }

  /** One reviewable row. Model output is untrusted text, so names go
   *  through textContent — never innerHTML. */
  function renderItem(item) {
    const row = document.createElement("li");
    row.className = "diary-entry estimate-item";

    const info = document.createElement("div");
    info.className = "diary-entry__info";
    const name = document.createElement("span");
    name.className = "diary-entry__name";
    name.textContent = item.name;
    const nutrition = document.createElement("span");
    nutrition.className = "diary-entry__amount";
    nutrition.textContent = formatNutrition(nutritionOf(item));
    info.append(name, nutrition);

    const gramsField = document.createElement("span");
    gramsField.className = "field-inline estimate-item__grams";
    const grams = document.createElement("input");
    Object.assign(grams, {
      type: "number",
      min: 1,
      max: 10000,
      step: 1,
      required: true,
      value: item.grams,
      inputMode: "numeric",
    });
    grams.setAttribute("aria-label", `Grams of ${item.name}`);
    const unit = document.createElement("span");
    unit.className = "field-inline__unit";
    unit.textContent = "g";
    gramsField.append(grams, unit);

    // Per-100 g nutrition means a corrected portion rescales everything with
    // one multiplication — the uncertain part of a photo estimate is the
    // weight, not what the food is.
    grams.addEventListener("input", () => {
      item.grams = Number(grams.value) || 0;
      nutrition.textContent = formatNutrition(nutritionOf(item));
      updateTotals();
    });

    const remove = document.createElement("button");
    remove.type = "button";
    remove.className = "diary-entry__delete";
    remove.textContent = "Remove";
    remove.setAttribute("aria-label", `Remove ${item.name}`);
    remove.addEventListener("click", () => {
      items = items.filter((i) => i !== item);
      row.remove();
      updateTotals();
    });

    row.append(info, gramsField, remove);
    return row;
  }

  function openReview(estimate) {
    items = estimate.items.map((item) => ({ ...item }));
    dialog.querySelector("[data-photo-note]").textContent =
      `${CONFIDENCE_LABELS[estimate.confidence]} · ${estimate.note}`;
    errorBox.hidden = true;
    form.elements.meal.value = defaultMeal();
    list.replaceChildren(...items.map(renderItem));
    updateTotals();
    dialog.showModal();
  }

  // A real button opening a hidden file input: keyboard- and screen-reader-
  // friendly, unlike styling the input itself. No `capture` attribute, so a
  // phone offers the camera *and* the photo library (a meal photographed
  // earlier can be logged too).
  button.addEventListener("click", () => input.click());

  input.addEventListener("change", async () => {
    const file = input.files[0];
    input.value = ""; // so picking the same photo again still fires "change"
    if (!file || busy) return; // one billed estimate at a time
    busy = true;
    button.disabled = true;
    button.textContent = "Estimating…";
    setNotice(status, "Preparing your photo…");

    try {
      let photo;
      try {
        photo = await downscaleToJpeg(file);
      } catch {
        setNotice(
          status,
          "Couldn't read that photo. Try a JPEG or PNG instead.",
          "error",
        );
        return;
      }

      setNotice(status, "Estimating the food in your photo…");
      const upload = new FormData();
      upload.append("photo", photo, "meal.jpg");
      const estimate = await apiFetch("/api/photo-estimates", {
        method: "POST",
        body: upload,
      });

      if (estimate.items.length === 0) {
        // Not food (or nothing recognisable): Claude's note says why.
        setNotice(status, estimate.note);
        return;
      }
      setNotice(status, null);
      openReview(estimate);
    } catch (error) {
      showRequestError(status, error);
    } finally {
      button.textContent = idleLabel;
      button.disabled = false;
      busy = false;
    }
  });

  dialog
    .querySelector("[data-cancel]")
    .addEventListener("click", () => dialog.close());

  // Native validation (required, min, max on each grams field) runs before
  // "submit" fires, so only a valid review gets here.
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (items.length === 0 || submit.disabled) return;
    const meal = form.elements.meal.value;
    submit.disabled = true;
    try {
      await apiFetch("/api/log/custom", {
        method: "POST",
        body: {
          meal_type: meal,
          items: items.map((item) => ({
            name: item.name,
            quantity_grams: item.grams,
            calories_per_100g: item.calories_per_100g,
            protein_per_100g: item.protein_per_100g,
            carbs_per_100g: item.carbs_per_100g,
            fat_per_100g: item.fat_per_100g,
          })),
        },
      });
      dialog.close();
      onLogged?.({ count: items.length, meal });
    } catch (error) {
      errorBox.textContent =
        error instanceof ApiError
          ? error.detail
          : "Couldn't reach FitTrack. Please try again.";
      errorBox.hidden = false;
    } finally {
      submit.disabled = items.length === 0;
    }
  });
}
