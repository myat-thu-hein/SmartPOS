/** Mirrors validate_password_strength in backend/app/core/security.py so obvious
 * mistakes are caught before submitting. The server remains authoritative. */
export function passwordProblems(password: string): string[] {
  const problems: string[] = [];
  if (password.length < 8) problems.push("At least 8 characters.");
  if (password.length > 128) problems.push("At most 128 characters.");
  // Combining marks count as letters, so a Thai word on its own is "letters only".
  if (/^\d+$/.test(password) || /^[\p{L}\p{M}]+$/u.test(password)) problems.push("Mix letters with numbers or symbols.");
  return problems;
}
