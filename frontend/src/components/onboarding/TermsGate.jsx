import { useCallback, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import {
  HiOutlineArrowRight,
  HiOutlineCheckCircle,
  HiOutlineDocumentText,
  HiOutlineLockClosed,
  HiOutlineShieldCheck,
  HiOutlineSparkles,
} from 'react-icons/hi2';
import TermsModal from './TermsModal';
import { setTermsAcceptance, TERMS_VERSION } from '../../utils/termsAcceptance';

const TRUST_POINTS = [
  {
    icon: HiOutlineShieldCheck,
    title: 'Controlled access',
    description: 'Only authorised accounts can access an organisation’s assessment workspace.',
  },
  {
    icon: HiOutlineLockClosed,
    title: 'Data safeguards',
    description: 'Safeguards are applied while organisational information is uploaded, reviewed and stored.',
  },
  {
    icon: HiOutlineSparkles,
    title: 'Traceable findings',
    description: 'Each finding is presented with its relevant evidence and recommended next action.',
  },
];

function Brand() {
  return (
    <div className="fin-brand">
      <span className="fin-brand-mark"><HiOutlineShieldCheck aria-hidden="true" /></span>
      <span className="fin-brand-copy">
        <strong>FinComply</strong>
        <small>DPDP readiness workspace</small>
      </span>
    </div>
  );
}

export default function TermsGate({ onAccept, user, onLogout }) {
  const [agreedTerms, setAgreedTerms] = useState(false);
  const [agreedAuthority, setAgreedAuthority] = useState(false);
  const [declined, setDeclined] = useState(false);
  const [showTerms, setShowTerms] = useState(false);

  const canContinue = agreedTerms && agreedAuthority;

  const handleAccept = useCallback(() => {
    if (!canContinue) return;
    setTermsAcceptance();
    onAccept();
  }, [canContinue, onAccept]);

  const handleDecline = useCallback(() => {
    setDeclined(true);
    setAgreedTerms(false);
    setAgreedAuthority(false);
  }, []);

  return (
    <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} className="fin-shell">
      <header className="fin-nav">
        <div className="fin-nav-inner">
          <Brand />
          <div className="flex items-center gap-3 sm:gap-5">
            <button type="button" onClick={() => setShowTerms(true)} className="text-sm font-semibold text-secondary hover:text-primary transition-colors">
              Read full terms
            </button>
            {user && (
              <span className="hidden sm:inline-flex items-center gap-2 text-xs text-secondary">
                <span className="h-8 w-8 rounded-xl grid place-items-center text-white font-bold bg-brand-secondary">
                  {(user.name || user.username || '?')[0].toUpperCase()}
                </span>
                {user.name || user.username}
              </span>
            )}
            {onLogout && (
              <button type="button" onClick={onLogout} className="action-secondary px-4 min-h-10 text-xs">Sign out</button>
            )}
          </div>
        </div>
      </header>

      <TermsModal isOpen={showTerms} onClose={() => setShowTerms(false)} />

      <main className="fin-page">
        <div className="onboarding-grid">
          <aside className="journey-panel" aria-label="Onboarding progress">
            <span className="eyebrow">Workspace setup · about 3 minutes</span>
            <h1>Set up your compliance review.</h1>
            <p>
              Confirm your authority, choose the assessment scope and review your organisation’s readiness in one secure workspace.
            </p>

            <div className="journey-steps">
              <div className="journey-step active">
                <span className="journey-step-number">1</span>
                <div><strong>Review and confirm</strong><span>Accept the terms and confirm your authority to proceed.</span></div>
              </div>
              <div className="journey-step">
                <span className="journey-step-number">2</span>
                <div><strong>Choose assessment scope</strong><span>Use your current workspace or provide updated records.</span></div>
              </div>
              <div className="journey-step">
                <span className="journey-step-number">3</span>
                <div><strong>Review results and actions</strong><span>Prioritise findings and download the assessment report.</span></div>
              </div>
            </div>

            <div className="journey-note">
              <HiOutlineDocumentText className="text-xl flex-shrink-0" aria-hidden="true" />
              <span>FinComply supports your internal review. It does not provide legal advice or regulatory certification.</span>
            </div>
          </aside>

          <section className="workspace-surface" aria-labelledby="welcome-title">
            <div className="workspace-header">
              <span className="section-eyebrow">Step 1 of 3 · Authorisation</span>
              <h2 id="welcome-title">Review and confirm</h2>
              <p>
                Confirm the terms of use and that you are authorised to begin an assessment for this organisation.
              </p>
            </div>

            <div className="workspace-body">
              <div className="plain-note">
                <HiOutlineCheckCircle className="text-xl flex-shrink-0" aria-hidden="true" />
                <span>
                  <strong className="block text-primary mb-1">Important responsibility</strong>
                  Your organisation is responsible for providing appropriate information and reviewing the findings before acting on them.
                </span>
              </div>

              <div className="trust-grid">
                {TRUST_POINTS.map(({ icon: Icon, title, description }) => (
                  <article className="trust-card" key={title}>
                    <Icon aria-hidden="true" />
                    <strong>{title}</strong>
                    <p>{description}</p>
                  </article>
                ))}
              </div>

              <div className="process-row" aria-label="Assessment journey">
                <div className="process-item"><strong>1. Confirm authority</strong><span>Accept the terms for this organisational assessment.</span></div>
                <HiOutlineArrowRight className="process-arrow" aria-hidden="true" />
                <div className="process-item"><strong>2. Select information</strong><span>Use your current workspace or provide an approved update.</span></div>
                <HiOutlineArrowRight className="process-arrow" aria-hidden="true" />
                <div className="process-item"><strong>3. Review readiness</strong><span>Prioritise findings and plan the next actions.</span></div>
              </div>

              <div className="acceptance-box">
                <p className="text-sm font-semibold text-primary mb-4">Confirm before continuing</p>
                <label className="acceptance-row" htmlFor="terms-checkbox">
                  <input
                    id="terms-checkbox"
                    className="acceptance-check"
                    type="checkbox"
                    checked={agreedTerms}
                    onChange={(event) => { setAgreedTerms(event.target.checked); setDeclined(false); }}
                  />
                  <span>
                    I have read and agree to the FinComply System Use Terms (version {TERMS_VERSION}).
                    <button type="button" onClick={(event) => { event.preventDefault(); setShowTerms(true); }} className="ml-1 font-semibold underline underline-offset-2 text-primary">
                      Review terms
                    </button>
                  </span>
                </label>
                <label className="acceptance-row" htmlFor="authority-checkbox">
                  <input
                    id="authority-checkbox"
                    className="acceptance-check"
                    type="checkbox"
                    checked={agreedAuthority}
                    onChange={(event) => { setAgreedAuthority(event.target.checked); setDeclined(false); }}
                  />
                  <span>I confirm that I am authorised to use this organisation’s data for a compliance assessment.</span>
                </label>
              </div>

              <AnimatePresence>
                {declined && (
                  <motion.p initial={{ opacity: 0, y: -5 }} animate={{ opacity: 1, y: 0 }} exit={{ opacity: 0 }} className="fin-error mt-4" role="alert">
                    Both confirmations are required before an organisational assessment can begin.
                  </motion.p>
                )}
              </AnimatePresence>

              <div className="mt-5 flex flex-col-reverse sm:flex-row gap-3 sm:justify-end">
                <button type="button" onClick={handleDecline} className="action-secondary px-6">Not now</button>
                <button type="button" disabled={!canContinue} onClick={handleAccept} className="action-primary px-7 inline-flex items-center justify-center gap-2">
                  Continue to data source <HiOutlineArrowRight aria-hidden="true" />
                </button>
              </div>
            </div>
          </section>
        </div>
      </main>
    </motion.div>
  );
}
