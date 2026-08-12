import { motion } from 'framer-motion';
import { HiOutlineCheckCircle } from 'react-icons/hi2';

const STEPS = [
  { id: 1, label: 'Terms & Data Use' },
  { id: 2, label: 'Organisation & Data' },
  { id: 3, label: 'Analysis' },
];

/**
 * OnboardingProgress
 * ==================
 * A 3-step horizontal progress indicator for the onboarding flow.
 *
 * Props:
 *   currentStep — 1 | 2 | 3
 */
export default function OnboardingProgress({ currentStep = 1 }) {
  return (
    <div className="flex items-center justify-center gap-1 sm:gap-2 flex-wrap">
      {STEPS.map((step, idx) => {
        const isCompleted = step.id < currentStep;
        const isActive = step.id === currentStep;

        return (
          <div key={step.id} className="flex items-center gap-1 sm:gap-2">
            {/* Step pill */}
            <motion.div
              initial={false}
              animate={{
                opacity: isActive || isCompleted ? 1 : 0.45,
              }}
              className="flex items-center gap-1.5"
            >
              {/* Step number or checkmark */}
              {isCompleted ? (
                <HiOutlineCheckCircle className="text-low text-base flex-shrink-0" />
              ) : (
                <span
                  className={`flex items-center justify-center h-5 w-5 rounded-full text-[10px] font-bold flex-shrink-0 ${
                    isActive
                      ? 'bg-brand-primary/20 text-brand-primary border border-brand-primary/40'
                      : 'bg-elevated text-muted border border-subtle'
                  }`}
                  style={{ color: isActive ? 'var(--brand-primary)' : undefined }}
                >
                  {step.id}
                </span>
              )}

              {/* Label */}
              <span
                className={`text-xs sm:text-sm font-medium whitespace-nowrap ${
                  isActive
                    ? 'text-primary'
                    : isCompleted
                      ? 'text-low'
                      : 'text-muted'
                }`}
              >
                {step.label}
              </span>
            </motion.div>

            {/* Arrow separator (not after last) */}
            {idx < STEPS.length - 1 && (
              <span className="text-muted text-xs mx-0.5 sm:mx-1 select-none">→</span>
            )}
          </div>
        );
      })}
    </div>
  );
}
