/**
 * Validator helpers for Datrix ``Validator.validateDatasets`` builtin.
 * Structural validation for parsed dataset collections.
 */

export function _validatorValidateDatasets(
  datasets: Record<string, unknown>,
): { isValid: boolean; errors: string[] } {
  const errors: string[] = [];
  if (typeof datasets !== 'object' || datasets === null || Array.isArray(datasets)) {
    return { isValid: false, errors: ['datasets must be an object'] };
  }
  for (const [name, records] of Object.entries(datasets)) {
    if (!Array.isArray(records)) {
      errors.push(`Dataset '${name}' must be an array, got ${typeof records}`);
    } else if (records.length === 0) {
      errors.push(`Dataset '${name}' is empty`);
    }
  }
  return { isValid: errors.length === 0, errors };
}
