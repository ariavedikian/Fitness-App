/** Meal-type helpers shared by the log dialog and the dashboard's meal ideas. */

/** Sensible default meal based on the time of day. Computed in the browser
 *  because only the browser knows the user's local time. */
export function defaultMeal() {
  const hour = new Date().getHours();
  if (hour < 11) return "breakfast";
  if (hour < 16) return "lunch";
  if (hour < 21) return "dinner";
  return "snack";
}
