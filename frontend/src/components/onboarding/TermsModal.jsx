import { useState, useCallback, useRef, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { HiOutlineXMark } from 'react-icons/hi2';
import { createPortal } from 'react-dom';
import { TERMS_VERSION, clearTermsAcceptance } from '../../utils/termsAcceptance';
import TermsContent from './TermsContent';

/**
 * TermsModal
 * ==========
 * A read-only modal for reviewing the System Use Terms after acceptance.
 * Includes an optional subtle "Reset Terms Acceptance" action for
 * development/user control.
 *
 * Props:
 *   isOpen        — boolean
 *   onClose       — () => void
 *   onReset       — () => void  (called after clearing acceptance)
 */
export default function TermsModal({ isOpen, onClose, onReset }) {
  const overlayRef = useRef(null);
  const closeButtonRef = useRef(null);
  const previousFocusRef = useRef(null);

  // Capture focus origin and manage focus
  useEffect(() => {
    if (isOpen) {
      previousFocusRef.current = document.activeElement;
      // Focus the close button after the modal animates in
      const timer = setTimeout(() => {
        closeButtonRef.current?.focus();
      }, 100);
      return () => clearTimeout(timer);
    } else if (previousFocusRef.current) {
      previousFocusRef.current.focus();
      previousFocusRef.current = null;
    }
  }, [isOpen]);

  // ESC to close
  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Prevent body scroll when modal is open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = 'hidden';
    } else {
      document.body.style.overflow = '';
    }
    return () => {
      document.body.style.overflow = '';
    };
  }, [isOpen]);

  const handleOverlayClick = useCallback(
    (e) => {
      if (e.target === overlayRef.current) {
        onClose();
      }
    },
    [onClose]
  );

  const [showResetConfirm, setShowResetConfirm] = useState(false);

  const handleReset = useCallback(() => {
    clearTermsAcceptance();
    setShowResetConfirm(false);
    onReset?.();
    onClose();
  }, [onReset, onClose]);

  const modalContent = (
    <AnimatePresence>
      {isOpen && (
        <motion.div
          ref={overlayRef}
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2 }}
          onClick={handleOverlayClick}
          className="fixed inset-0 z-[100] flex items-start justify-center bg-black/60 backdrop-blur-sm overflow-y-auto py-8 px-4"
          role="dialog"
          aria-modal="true"
          aria-label="System Use Terms"
        >
          <motion.div
            initial={{ opacity: 0, y: 20, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 20, scale: 0.98 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="relative w-full max-w-3xl bg-surface rounded-xl border border-subtle shadow-card"
          >
            {/* Modal header */}
            <div className="sticky top-0 z-10 flex items-center justify-between p-5 border-b border-subtle bg-surface rounded-t-xl">
              <div className="flex items-center gap-3">
                <h2 className="text-h3 text-primary">System Use Terms</h2>
                <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-elevated text-secondary border border-subtle">
                  v{TERMS_VERSION}
                </span>
              </div>
              <button
                ref={closeButtonRef}
                onClick={onClose}
                className="p-2 text-secondary hover:text-primary hover:bg-elevated rounded-lg transition-colors"
                aria-label="Close terms modal"
              >
                <HiOutlineXMark className="text-xl" />
              </button>
            </div>

            {/* Scrollable terms content */}
            <div className="p-6 sm:p-8 max-h-[65vh] overflow-y-auto terms-scrollbar">
              <TermsContent />
            </div>

            {/* Modal footer */}
            <div className="flex items-center justify-between p-5 border-t border-subtle bg-base/30 rounded-b-xl">
              <div>
                {!showResetConfirm ? (
                  <button
                    onClick={() => setShowResetConfirm(true)}
                    className="text-xs text-muted hover:text-secondary transition-colors"
                  >
                    Reset Terms Acceptance
                  </button>
                ) : (
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-secondary">
                      This will require re-acceptance.
                    </span>
                    <button
                      onClick={handleReset}
                      className="text-xs text-red-400 hover:text-red-300 font-medium transition-colors"
                    >
                      Confirm Reset
                    </button>
                    <button
                      onClick={() => setShowResetConfirm(false)}
                      className="text-xs text-muted hover:text-secondary transition-colors"
                    >
                      Cancel
                    </button>
                  </div>
                )}
              </div>
              <button
                onClick={onClose}
                className="px-4 py-2 text-sm font-medium text-secondary hover:text-primary border border-subtle rounded-lg hover:bg-elevated transition-colors"
              >
                Close
              </button>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );

  return createPortal(modalContent, document.body);
}
