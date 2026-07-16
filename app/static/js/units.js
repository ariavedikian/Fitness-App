/**
 * Unit conversions between what US users type (feet/inches, pounds) and what
 * the API stores (centimetres, kilograms).
 *
 * Kept as pure functions in their own module: the storage layer stays metric
 * everywhere, and the imperial ↔ metric knowledge lives in exactly one place
 * instead of being scattered through the form code.
 */

export const CM_PER_INCH = 2.54;
export const INCHES_PER_FOOT = 12;
export const KG_PER_LB = 0.45359237;

/** Feet and inches to centimetres. */
export function feetInchesToCm(feet, inches) {
  return (feet * INCHES_PER_FOOT + inches) * CM_PER_INCH;
}

/** Centimetres to whole feet and inches, for pre-filling the form. */
export function cmToFeetInches(cm) {
  const totalInches = Math.round(cm / CM_PER_INCH);
  return {
    feet: Math.trunc(totalInches / INCHES_PER_FOOT),
    inches: totalInches % INCHES_PER_FOOT,
  };
}

/** Pounds to kilograms. */
export function lbsToKg(lbs) {
  return lbs * KG_PER_LB;
}

/** Kilograms to pounds. */
export function kgToLbs(kg) {
  return kg / KG_PER_LB;
}
