import { useState, useCallback } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  HiOutlineShieldCheck,
  HiOutlineLockClosed,
  HiOutlineSparkles,
} from 'react-icons/hi2';
import Card from '../ui/Card';
import OnboardingProgress from './OnboardingProgress';
import TermsContent from './TermsContent';
import { setTermsAcceptance, TERMS_VERSION } from '../../utils/termsAcceptance';

const TRUST_CARDS = [
  {
    icon: HiOutlineShieldCheck,
    title: 'Deterministic Compliance Rules',
    description:
      'Core compliance findings are evaluated against structured DPDP and internal policy rules rather than being decided solely by a generative AI model.',
  },
  {
    icon: HiOutlineLockClosed,
    title: 'Privacy-Aware Processing',
    description:
      'Supported identifiers are pseudonymized before compliance analysis and raw upload copies are used only during ingestion.',
  },
  {
    icon: HiOutlineSparkles,
    title: 'Explainable Intelligence',
    description:
      'Machine-learning and AI components assist with risk prediction and explanations while deterministic findings remain traceable to rules and evidence signals.',
  },
];

const fadeUp = {
  initial: { opacity: 0, y: 16 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: -8 },
};

/**
 * TermsGate
 * =========
 * Step 1 of the onboarding flow.
 * Full-page Terms & System Use acceptance screen.
 *
 * The organisation/upload interface is NOT rendered until the user
 * explicitly accepts both checkboxes and clicks "Accept & Continue".
 *
 * Props:
 *   onAccept — () => void  (called after storing versioned acceptance)
 */
export default function TermsGate({ onAccept }) {
  const [agreedTerms, setAgreedTerms] = useState(false);
  const [agreedAuthority, setAgreedAuthority] = useState(false);
  const [declined, setDeclined] = useState(false);

  const canContinue = agreedTerms && agreedAuthority;

  const handleAccept = useCallback(() => {
    if (!canContinue) return;
    setTermsAcceptance();
    onAccept();
  }, [canContinue, onAccept]);

  const handleDecline = useCallback(() => {
    setDeclined(true);
    // Reset checkboxes when declining
    setAgreedTerms(false);
    setAgreedAuthority(false);
  }, []);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="min-h-screen relative"
    >
      {/* Top Nav */}
      <nav className="h-16 flex items-center justify-between px-6 border-b border-subtle bg-base/50 backdrop-blur-md sticky top-0 z-10">
        <div className="flex items-center gap-2">
          <span className="font-bold text-lg tracking-tight">Fin-Comply</span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-elevated text-secondary border border-subtle">
            v{TERMS_VERSION}
          </span>
        </div>
        <span className="text-sm text-secondary">System Use Terms</span>
      </nav>

      <main className="container-center pb-24">
        {/* Header */}
        <div className="pt-16 sm:pt-20 max-w-[720px] mx-auto text-center">
          <motion.span
            {...fadeUp}
            transition={{ delay: 0.1 }}
            className="inline-block px-3 py-1 rounded-full text-xs font-medium border border-subtle bg-elevated/50 text-secondary mb-6"
          >
            DPDP Compliance Intelligence
          </motion.span>

          <motion.h1
            {...fadeUp}
            transition={{ delay: 0.2 }}
            className="text-display mb-4"
          >
            Before you begin
          </motion.h1>

          <motion.p
            {...fadeUp}
            transition={{ delay: 0.3 }}
            className="text-body text-secondary max-w-[600px] mx-auto mb-8"
          >
            Please review how Fin-Comply processes organisational compliance data and how automated
            analysis is used before starting an assessment.
          </motion.p>

          {/* Progress indicator */}
          <motion.div {...fadeUp} transition={{ delay: 0.35 }}>
            <OnboardingProgress currentStep={1} />
          </motion.div>
        </div>

        {/* Trust cards */}
        <motion.div
          {...fadeUp}
          transition={{ delay: 0.4 }}
          className="mt-12 max-w-[880px] mx-auto grid grid-cols-1 md:grid-cols-3 gap-4"
        >
          {TRUST_CARDS.map((card) => {
            const Icon = card.icon;
            return (
              <Card key={card.title} className="p-5">
                <div className="flex items-start gap-3">
                  <div className="h-9 w-9 rounded-lg bg-brand-primary/10 flex items-center justify-center flex-shrink-0 border border-brand-primary/20">
                    <Icon className="text-lg" style={{ color: 'var(--brand-primary)' }} />
                  </div>
                  <div>
                    <h4 className="text-sm font-semibold text-primary mb-1">{card.title}</h4>
                    <p className="text-xs leading-relaxed text-secondary">{card.description}</p>
                  </div>
                </div>
              </Card>
            );
          })}
        </motion.div>

        {/* Terms card */}
        <motion.div
          {...fadeUp}
          transition={{ delay: 0.5 }}
          className="mt-8 max-w-[880px] mx-auto"
        >
          <Card className="overflow-hidden">
            {/* Card header */}
            <div className="p-6 sm:p-8 pb-4 border-b border-subtle bg-base/30">
              <div className="flex items-center gap-3 mb-1">
                <h2 className="text-h2 text-primary">System Use Terms</h2>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-elevated text-secondary border border-subtle">
                  v{TERMS_VERSION}
                </span>
              </div>
              <p className="text-caption">
                Please read the following terms carefully before proceeding.
              </p>
            </div>

            {/* Scrollable terms content */}
            <div className="p-6 sm:p-8 max-h-[50vh] overflow-y-auto terms-scrollbar">
              <TermsContent />
            </div>

            {/* Acceptance controls */}
            <div className="p-6 sm:p-8 pt-4 border-t border-subtle bg-base/30 space-y-4">
              {/* Checkbox 1 */}
              <label
                htmlFor="terms-checkbox"
                className="flex items-start gap-3 cursor-pointer group"
              >
                <div className="relative flex-shrink-0 mt-0.5">
                  <input
                    type="checkbox"
                    id="terms-checkbox"
                    checked={agreedTerms}
                    onChange={(e) => {
                      setAgreedTerms(e.target.checked);
                      if (declined) setDeclined(false);
                    }}
                    className="peer sr-only"
                  />
                  <div
                    className={`h-5 w-5 rounded border-2 transition-all flex items-center justify-center ${
                      agreedTerms
                        ? 'bg-brand-primary border-brand-primary'
                        : 'bg-elevated border-subtle group-hover:border-brand-primary/50'
                    }`}
                    aria-hidden="true"
                  >
                    {agreedTerms && (
                      <motion.svg
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="h-3 w-3 text-white"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={3}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </motion.svg>
                    )}
                  </div>
                </div>
                <span className="text-sm text-secondary group-hover:text-primary transition-colors select-none">
                  I have read and agree to the Fin-Comply System Use Terms.
                </span>
              </label>

              {/* Checkbox 2 */}
              <label
                htmlFor="authority-checkbox"
                className="flex items-start gap-3 cursor-pointer group"
              >
                <div className="relative flex-shrink-0 mt-0.5">
                  <input
                    type="checkbox"
                    id="authority-checkbox"
                    checked={agreedAuthority}
                    onChange={(e) => {
                      setAgreedAuthority(e.target.checked);
                      if (declined) setDeclined(false);
                    }}
                    className="peer sr-only"
                  />
                  <div
                    className={`h-5 w-5 rounded border-2 transition-all flex items-center justify-center ${
                      agreedAuthority
                        ? 'bg-brand-primary border-brand-primary'
                        : 'bg-elevated border-subtle group-hover:border-brand-primary/50'
                    }`}
                    aria-hidden="true"
                  >
                    {agreedAuthority && (
                      <motion.svg
                        initial={{ scale: 0 }}
                        animate={{ scale: 1 }}
                        className="h-3 w-3 text-white"
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                        strokeWidth={3}
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </motion.svg>
                    )}
                  </div>
                </div>
                <span className="text-sm text-secondary group-hover:text-primary transition-colors select-none">
                  I confirm that I am authorised to submit the organisation&apos;s data for this assessment.
                </span>
              </label>

              {/* Decline message */}
              <AnimatePresence>
                {declined && (
                  <motion.div
                    initial={{ opacity: 0, height: 0 }}
                    animate={{ opacity: 1, height: 'auto' }}
                    exit={{ opacity: 0, height: 0 }}
                    className="overflow-hidden"
                  >
                    <p className="text-sm text-amber-400/90 bg-amber-500/10 border border-amber-500/20 rounded-lg px-4 py-3">
                      You must accept the System Use Terms before starting a compliance assessment.
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>

              {/* Action buttons */}
              <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-2">
                <button
                  disabled={!canContinue}
                  onClick={handleAccept}
                  className={`flex-1 h-12 rounded-lg font-medium text-white transition-all flex items-center justify-center gap-2 ${
                    canContinue
                      ? 'btn-gradient shadow-glow hover:opacity-90 cursor-pointer'
                      : 'bg-elevated text-muted cursor-not-allowed border border-subtle'
                  }`}
                  aria-disabled={!canContinue}
                >
                  Accept &amp; Continue
                </button>
                <button
                  onClick={handleDecline}
                  className="px-6 h-12 rounded-lg text-sm font-medium text-secondary hover:text-primary border border-subtle hover:bg-elevated transition-colors"
                >
                  Decline
                </button>
              </div>
            </div>
          </Card>
        </motion.div>

        <footer className="mt-16 text-center text-caption text-muted">
          Fin-Comply v{TERMS_VERSION} • Decision-Support System • DPDP Act 2023
        </footer>
      </main>
    </motion.div>
  );
}
