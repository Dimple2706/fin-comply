/**
 * termsAcceptance.js
 * ==================
 * Versioned localStorage helpers for the Fin-Comply System Use Terms
 * acceptance gate.
 *
 * This is a UX onboarding mechanism, NOT a security boundary or
 * legally-auditable consent record. Backend JWT/RBAC remains
 * responsible for access control.
 */

export const TERMS_VERSION = '1.0';
export const STORAGE_KEY = 'fincomply_terms_acceptance';

/**
 * Safely read and validate the stored Terms acceptance object.
 *
 * Returns `true` only when:
 *   - localStorage contains valid JSON under STORAGE_KEY
 *   - `accepted === true`
 *   - `version` matches the current TERMS_VERSION
 *
 * Returns `false` for missing, malformed, or version-mismatched data
 * without throwing.
 */
export function getTermsAcceptance() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;

    const parsed = JSON.parse(raw);

    if (
      parsed &&
      typeof parsed === 'object' &&
      parsed.accepted === true &&
      parsed.version === TERMS_VERSION
    ) {
      return true;
    }

    return false;
  } catch {
    // Malformed JSON or localStorage access failure — never crash
    return false;
  }
}

/**
 * Persist a versioned acceptance record to localStorage.
 */
export function setTermsAcceptance() {
  try {
    const record = {
      accepted: true,
      version: TERMS_VERSION,
      acceptedAt: new Date().toISOString(),
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(record));
  } catch {
    // Storage full or blocked — acceptance won't persist across refreshes
    // but the in-memory state in the React component will still work
    // for the current session.
    console.warn('[Fin-Comply] Unable to persist Terms acceptance to localStorage.');
  }
}

/**
 * Remove the stored acceptance record.
 * Used for development/testing or when TERMS_VERSION changes.
 */
export function clearTermsAcceptance() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Silently ignore
  }
}
