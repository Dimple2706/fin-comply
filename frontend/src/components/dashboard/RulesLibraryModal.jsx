import { useEffect, useMemo, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { createPortal } from 'react-dom';
import {
  HiOutlineBookOpen,
  HiOutlineMagnifyingGlass,
  HiOutlineXMark,
} from 'react-icons/hi2';
import { getRules } from '../../services/api';

const SEVERITY_STYLES = {
  CRITICAL: 'border-red-200 bg-red-50 text-red-700',
  HIGH: 'border-orange-200 bg-orange-50 text-orange-700',
  MEDIUM: 'border-amber-200 bg-amber-50 text-amber-700',
  LOW: 'border-green-200 bg-green-50 text-green-700',
};

export default function RulesLibraryModal({ isOpen, onClose }) {
  const [rules, setRules] = useState([]);
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const closeButtonRef = useRef(null);
  const previousFocusRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return undefined;

    previousFocusRef.current = document.activeElement;
    document.body.style.overflow = 'hidden';
    const focusTimer = setTimeout(() => closeButtonRef.current?.focus(), 100);

    const handleKeyDown = (event) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', handleKeyDown);

    return () => {
      clearTimeout(focusTimer);
      document.removeEventListener('keydown', handleKeyDown);
      document.body.style.overflow = '';
      previousFocusRef.current?.focus();
    };
  }, [isOpen, onClose]);

  useEffect(() => {
    if (!isOpen || rules.length > 0) return;

    let active = true;
    getRules()
      .then((items) => {
        if (!active) return;
        setRules(items.filter((item) => item.rule_id?.startsWith('DPDP-') && item.enabled));
      })
      .catch((requestError) => {
        if (active) setError(requestError.message || 'The rules could not be loaded.');
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [isOpen, rules.length]);

  const visibleRules = useMemo(() => {
    const normalisedQuery = query.trim().toLowerCase();
    if (!normalisedQuery) return rules;
    return rules.filter((rule) => (
      `${rule.rule_id} ${rule.rule_name} ${rule.dpdp_section} ${rule.description}`
        .toLowerCase()
        .includes(normalisedQuery)
    ));
  }, [query, rules]);

  const content = (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[100] flex items-end justify-center bg-[#211923]/70 backdrop-blur-sm sm:items-center sm:p-6"
          onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}
          role="presentation"
        >
          <motion.section
            initial={{ opacity: 0, y: 28, scale: 0.985 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 28, scale: 0.985 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="flex h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-t-3xl border border-subtle bg-surface shadow-card sm:h-[88vh] sm:rounded-3xl"
            role="dialog"
            aria-modal="true"
            aria-labelledby="rules-library-title"
          >
            <header className="border-b border-subtle bg-surface px-5 py-5 sm:px-8 sm:py-6">
              <div className="flex items-start justify-between gap-5">
                <div className="flex items-start gap-4">
                  <span className="grid h-11 w-11 flex-none place-items-center rounded-2xl bg-brand-secondary text-white">
                    <HiOutlineBookOpen className="text-xl" aria-hidden="true" />
                  </span>
                  <div>
                    <p className="text-label text-copper">Assessment reference</p>
                    <h2 id="rules-library-title" className="mt-1 text-h2 text-primary">DPDP assessment rules</h2>
                    <p className="mt-1 max-w-2xl text-sm text-secondary">
                      Review the checks FinComply applies and the DPDP provision associated with each check.
                    </p>
                  </div>
                </div>
                <button
                  ref={closeButtonRef}
                  type="button"
                  onClick={onClose}
                  className="rounded-xl p-2.5 text-secondary transition-colors hover:bg-elevated hover:text-primary"
                  aria-label="Close DPDP rules"
                >
                  <HiOutlineXMark className="text-2xl" />
                </button>
              </div>

              <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <label className="relative block w-full sm:max-w-md">
                  <HiOutlineMagnifyingGlass className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-lg text-muted" aria-hidden="true" />
                  <span className="sr-only">Search assessment rules</span>
                  <input
                    type="search"
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search by rule, topic or section"
                    className="h-11 w-full rounded-xl border border-subtle bg-base pl-11 pr-4 text-sm text-primary outline-none transition focus:border-brand-primary focus:ring-2 focus:ring-brand-primary/10"
                  />
                </label>
                <p className="text-sm font-semibold text-secondary">
                  {loading ? 'Loading checks…' : `${visibleRules.length} of ${rules.length} checks`}
                </p>
              </div>
            </header>

            <div className="terms-scrollbar flex-1 overflow-y-auto px-5 py-5 sm:px-8 sm:py-6">
              <div className="mb-5 rounded-2xl border border-brand-primary/20 bg-brand-primary/10 px-4 py-3 text-sm leading-relaxed text-secondary">
                These are FinComply’s evidence-based assessment checks mapped to DPDP provisions. They are not a substitute for the official legal text or professional legal advice.
              </div>

              {error && (
                <div className="rounded-2xl border border-red-200 bg-red-50 px-4 py-4 text-sm text-red-700" role="alert">
                  {error}
                </div>
              )}

              {loading && (
                <div className="grid gap-3 sm:grid-cols-2" aria-label="Loading rules">
                  {Array.from({ length: 6 }).map((_, index) => (
                    <div key={index} className="h-40 animate-pulse rounded-2xl border border-subtle bg-elevated/60" />
                  ))}
                </div>
              )}

              {!loading && !error && visibleRules.length === 0 && (
                <div className="rounded-2xl border border-subtle bg-base px-5 py-10 text-center text-sm text-secondary">
                  No assessment rule matches your search.
                </div>
              )}

              {!loading && !error && visibleRules.length > 0 && (
                <div className="grid gap-3 sm:grid-cols-2">
                  {visibleRules.map((rule) => (
                    <article key={rule.rule_id} className="rounded-2xl border border-subtle bg-[#fbf7f1] p-5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <span className="font-mono text-xs font-bold tracking-wide text-brand-primary">{rule.rule_id}</span>
                        <span className={`rounded-full border px-2.5 py-1 text-[10px] font-bold tracking-wide ${SEVERITY_STYLES[rule.severity] || 'border-subtle bg-elevated text-secondary'}`}>
                          {rule.severity}
                        </span>
                      </div>
                      <h3 className="mt-4 text-base font-bold leading-snug text-primary">{rule.rule_name}</h3>
                      <p className="mt-2 text-xs font-semibold uppercase tracking-wide text-copper">{rule.dpdp_section}</p>
                      <p className="mt-3 text-sm leading-relaxed text-secondary">{rule.description}</p>
                    </article>
                  ))}
                </div>
              )}
            </div>

            <footer className="flex items-center justify-between gap-4 border-t border-subtle bg-base/60 px-5 py-4 sm:px-8">
              <p className="hidden text-xs text-muted sm:block">Use this reference while reviewing findings and remediation priorities.</p>
              <button type="button" onClick={onClose} className="action-secondary ml-auto min-h-11 px-6">Close</button>
            </footer>
          </motion.section>
        </motion.div>
      )}
    </AnimatePresence>
  );

  return createPortal(content, document.body);
}
