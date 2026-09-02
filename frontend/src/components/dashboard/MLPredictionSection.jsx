import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { 
  HiOutlineCpuChip, 
  HiOutlineChartBar, 
  HiOutlineArrowTrendingUp, 
  HiOutlineArrowTrendingDown,
  HiOutlineCheckCircle,
  HiOutlineExclamationTriangle,
  HiOutlineInformationCircle,
  HiOutlineShieldCheck,
  HiChevronDown,
  HiChevronUp
} from 'react-icons/hi2';
import Card from '../ui/Card';

const TIER_COLORS = {
  COMPLIANT: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30', fill: '#22c55e' },
  LOW: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30', fill: '#3b82f6' },
  MEDIUM: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', fill: '#eab308' },
  HIGH: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30', fill: '#f97316' },
  CRITICAL: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', fill: '#ef4444' },
};

const TIER_RANK = { COMPLIANT: 0, LOW: 1, MEDIUM: 2, HIGH: 3, CRITICAL: 4 };

const FEATURE_LABEL_MAP = {
  n_violations: 'Total compliance findings',
  n_warnings: 'Total warnings',
  n_critical_rules_fired: 'Critical rules triggered',
  n_high_rules_fired: 'High-severity rules triggered',
  breach_rule_fired: 'Personal-data breach detected',
  minor_data_rule_fired: "Children's data violation detected",
  max_rule_score: 'Highest rule score',
  max_prevalence_ratio: 'Highest prevalence ratio',
  consent_violation_count: 'Consent-related findings',
  retention_violation_count: 'Retention-related findings',
  encryption_violation_count: 'Encryption-related findings',
  access_violation_count: 'Unauthorised access findings',
  policy_violation_count: 'Internal policy findings',
  total_penalty_exposure: 'Maximum statutory exposure (₹ crore)',
};

/**
 * Format a feature value for display. Binary features show Yes/No,
 * currency features show ₹ prefix, others show the number.
 */
function formatFeatureValue(featureName, value) {
  if (featureName === 'breach_rule_fired' || featureName === 'minor_data_rule_fired') {
    return value >= 1 ? 'Yes' : 'No';
  }
  if (featureName === 'total_penalty_exposure') {
    return `₹${Number(value).toLocaleString()} Cr`;
  }
  return Number(value).toLocaleString();
}

/**
 * Determine human-friendly impact level from LIME coefficient magnitude.
 */
function getLimeImpactLabel(coeff) {
  const abs = Math.abs(coeff);
  if (abs >= 0.15) return { label: 'High Impact Driver', badgeClass: 'bg-red-500/20 text-red-300 border-red-500/30' };
  if (abs >= 0.05) return { label: 'Moderate Impact Driver', badgeClass: 'bg-orange-500/20 text-orange-300 border-orange-500/30' };
  return { label: 'Low Impact Driver', badgeClass: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30' };
}

/**
 * Parse a raw LIME condition string (e.g. "n_violations > 221.00") to
 * extract the underlying feature name and map it to a readable label.
 */
function parseLimeCondition(rawCondition) {
  for (const [key, label] of Object.entries(FEATURE_LABEL_MAP)) {
    if (rawCondition.includes(key)) {
      return { label, featureName: key };
    }
  }
  return { label: rawCondition, featureName: null };
}

/**
 * Determine the comparison message when ML and deterministic tiers differ.
 */
function tierComparisonMessage(mlTier, detTier) {
  const mlRank = TIER_RANK[mlTier] ?? 0;
  const detRank = TIER_RANK[detTier] ?? 0;
  if (mlRank > detRank) {
    return 'The ML cross-check is more cautious than the primary assessment.';
  }
  if (mlRank < detRank) {
    return 'The ML cross-check is less cautious than the primary assessment.';
  }
  return 'Both assessments agree.';
}

export default function MLPredictionSection({ mlData, deterministicTier, deterministicScore }) {
  const [showShapDetails, setShowShapDetails] = useState(false);

  if (!mlData || mlData.ml_available === false) {
    return (
      <motion.section 
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.15 }}
        className="mb-8"
      >
        <Card className="p-6 border border-subtle bg-surface">
          <div className="flex items-center gap-3 text-secondary">
            <HiOutlineInformationCircle className="text-xl text-yellow-400" />
            <span className="text-sm">
              AI Risk Classifier is operating in rule-fallback mode for this profile.
            </span>
          </div>
        </Card>
      </motion.section>
    );
  }

  const {
    predicted_tier,
    probabilities = {},
    shap_explanation = {},
    lime_explanation = {},
    feature_vector = {},
  } = mlData;
  const predStyle = TIER_COLORS[predicted_tier] || TIER_COLORS.MEDIUM;
  const detStyle = TIER_COLORS[deterministicTier] || TIER_COLORS.MEDIUM;

  // Filter SHAP to ignore 0-impact items
  const shapContributions = (shap_explanation.feature_contributions || [])
    .filter((item) => Math.abs(item.shap_value) > 0.0001);
  const topPositiveShap = shapContributions
    .filter((item) => item.direction === 'positive')
    .slice(0, 5);
  const topNegativeShap = shapContributions
    .filter((item) => item.direction === 'negative')
    .slice(0, 5);

  // Filter LIME to ignore 0-impact items
  const limeContributions = (lime_explanation.feature_contributions || [])
    .filter((item) => Math.abs(item.coefficient) > 0.001)
    .slice(0, 8);
  const limePositive = limeContributions.filter((item) => item.direction === 'positive');
  const limeNegative = limeContributions.filter((item) => item.direction === 'negative');

  // Backend sends probabilities as percentages (0-100) — use directly
  const confPct = probabilities[predicted_tier] || 0;
  const probTotal = Object.values(probabilities).reduce((sum, v) => sum + v, 0);
  const tiersMatch = predicted_tier === deterministicTier;

  return (
    <motion.section
      initial={{ opacity: 0, y: 15 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.15 }}
      className="mb-8"
    >
      {/* Section Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 mb-4">
        <div className="flex items-center gap-3">
          <div className="h-9 w-9 rounded-lg bg-brand-primary/10 flex items-center justify-center text-brand-primary border border-brand-primary/20">
            <HiOutlineCpuChip className="text-xl" />
          </div>
          <div>
            <h3 className="text-h3 text-primary flex items-center gap-2">
              AI Risk Cross-Check
            </h3>
            <p className="text-caption text-secondary">
              An advisory machine-learning prediction that cross-verifies your compliance score.
            </p>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* CARD 1: Primary Assessment & ML Cross-Check (4 cols) */}
        <Card className="lg:col-span-4 p-6 bg-surface border border-subtle flex flex-col justify-between">
          <div>
            {/* Primary Compliance Assessment */}
            <div className="p-4 rounded-xl border border-subtle bg-base/50 mb-4">
              <div className="text-caption text-secondary uppercase font-semibold tracking-wider flex items-center gap-1.5">
                <HiOutlineShieldCheck className="text-sm" />
                Primary Compliance Assessment
              </div>
              <div className={`text-lg font-bold font-mono mt-1 ${detStyle.text}`}>
                {deterministicTier} — Score {deterministicScore}/100
              </div>
              <p className="text-caption text-secondary mt-1">
                Calculated from the organisation&apos;s DPDP assessment findings.
              </p>
            </div>

            {/* ML Risk Cross-Check */}
            <div className={`p-4 rounded-xl border mb-4 ${predStyle.bg} ${predStyle.border}`}>
              <div className="text-caption text-secondary uppercase font-semibold tracking-wider flex items-center gap-1.5">
                <HiOutlineCpuChip className="text-sm" />
                AI Risk Cross-Check
              </div>
              <div className={`text-2xl font-bold font-mono mt-1 ${predStyle.text}`}>
                {predicted_tier}
              </div>
              <div className="text-caption text-secondary mt-1">
                <strong className="text-primary font-mono">{confPct.toFixed(1)}%</strong> AI confidence
              </div>
            </div>

            {/* Tier comparison */}
            <div className="p-3 rounded-lg bg-base/50 border border-subtle">
              <div className="text-caption text-secondary flex items-center gap-1.5">
                {tiersMatch ? (
                  <span className="text-low flex items-center gap-1">
                    <HiOutlineCheckCircle className="text-sm" /> Both assessments agree
                  </span>
                ) : (
                  <>
                    <HiOutlineExclamationTriangle className="text-sm text-medium" />
                    <span className="text-medium">
                      {tierComparisonMessage(predicted_tier, deterministicTier)}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Probability Distribution */}
          <div className="mt-6 pt-4 border-t border-subtle">
            <span className="text-caption text-secondary block mb-2 font-medium">
              Probability Distribution
            </span>
            <div className="space-y-2">
              {['COMPLIANT', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((tier) => {
                const prob = probabilities[tier] || 0;
                const style = TIER_COLORS[tier];
                return (
                  <div key={tier} className="text-caption">
                    <div className="flex justify-between items-center mb-0.5">
                      <span className="text-secondary font-mono">{tier}</span>
                      <span className="text-primary font-mono">{prob.toFixed(1)}%</span>
                    </div>
                    <div className="h-1.5 w-full bg-elevated rounded-full overflow-hidden">
                      <div 
                        className="h-full rounded-full transition-all duration-500"
                        style={{ width: `${prob}%`, backgroundColor: style.fill }}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
            <div className="mt-2 text-caption text-muted text-right font-mono">
              Total: {probTotal.toFixed(1)}%
            </div>
          </div>
        </Card>

        {/* CARD 2: Customer-Friendly AI Explanation (LIME - 8 cols) */}
        <Card className="lg:col-span-8 p-6 bg-surface border border-subtle">
          <div className="flex items-center justify-between gap-4 mb-4">
            <div>
              <h4 className="text-h4 text-primary flex items-center gap-2">
                <HiOutlineChartBar className="text-brand-primary" />
                AI Risk Explanation (LIME Analysis)
              </h4>
              <p className="text-caption text-secondary mt-0.5">
                500 scenario simulations revealed these key factors driving your {predicted_tier} risk prediction:
              </p>
            </div>
          </div>

          {limeContributions.length === 0 ? (
            <p className="text-caption text-muted italic">No significant risk drivers detected.</p>
          ) : (
            <div className="space-y-5">
              {/* Factors Pushing Risk Higher */}
              {limePositive.length > 0 && (
                <div>
                  <span className="text-caption text-red-400 font-semibold uppercase tracking-wider flex items-center gap-1 mb-3">
                    <HiOutlineArrowTrendingUp className="text-base" />
                    Factors Pushing Risk Higher
                  </span>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {limePositive.map((item, idx) => {
                      const { label, featureName } = parseLimeCondition(item.feature);
                      const currentVal = featureName ? feature_vector[featureName] : null;
                      const displayVal = currentVal !== null && currentVal !== undefined 
                        ? formatFeatureValue(featureName, currentVal) 
                        : null;
                      const { label: impactText } = getLimeImpactLabel(item.coefficient);

                      return (
                        <div key={`pos-${idx}`} className="p-3.5 rounded-xl bg-base/60 border border-subtle flex flex-col justify-between gap-2">
                          <div className="flex items-start justify-between gap-2">
                            <span className="text-sm font-medium text-primary leading-snug">
                              {label}
                            </span>
                            <span className="shrink-0 px-2 py-0.5 rounded text-[11px] font-semibold bg-red-500/10 text-red-400 border border-red-500/20">
                              Risk Increaser
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-caption text-muted pt-1 border-t border-subtle/50">
                            <span>{impactText}</span>
                            {displayVal && (
                              <span className="font-mono text-primary font-semibold">Value: {displayVal}</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Factors Reducing Risk */}
              {limeNegative.length > 0 && (
                <div>
                  <span className="text-caption text-green-400 font-semibold uppercase tracking-wider flex items-center gap-1 mb-3">
                    <HiOutlineArrowTrendingDown className="text-base" />
                    Factors Helping Lower Risk
                  </span>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                    {limeNegative.map((item, idx) => {
                      const { label, featureName } = parseLimeCondition(item.feature);
                      const currentVal = featureName ? feature_vector[featureName] : null;
                      const displayVal = currentVal !== null && currentVal !== undefined 
                        ? formatFeatureValue(featureName, currentVal) 
                        : null;
                      const { label: impactText } = getLimeImpactLabel(item.coefficient);

                      return (
                        <div key={`neg-${idx}`} className="p-3.5 rounded-xl bg-base/60 border border-subtle flex flex-col justify-between gap-2">
                          <div className="flex items-start justify-between gap-2">
                            <span className="text-sm font-medium text-primary leading-snug">
                              {label}
                            </span>
                            <span className="shrink-0 px-2 py-0.5 rounded text-[11px] font-semibold bg-green-500/10 text-green-400 border border-green-500/20">
                              Risk Reducer
                            </span>
                          </div>
                          <div className="flex items-center justify-between text-caption text-muted pt-1 border-t border-subtle/50">
                            <span>{impactText}</span>
                            {displayVal && (
                              <span className="font-mono text-primary font-semibold">Value: {displayVal}</span>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Collapsible SHAP Panel Toggle Button */}
          <div className="mt-6 pt-4 border-t border-subtle flex items-center justify-between">
            <span className="text-caption text-muted">
              Need detailed mathematical feature attributions?
            </span>
            <button
              type="button"
              onClick={() => setShowShapDetails(!showShapDetails)}
              className="px-3 py-1.5 rounded-lg text-xs font-semibold text-brand-primary border border-brand-primary/30 hover:bg-brand-primary/10 transition-colors flex items-center gap-1.5"
            >
              {showShapDetails ? (
                <>Hide Mathematical SHAP Breakdown <HiChevronUp className="text-sm" /></>
              ) : (
                <>View Mathematical SHAP Breakdown <HiChevronDown className="text-sm" /></>
              )}
            </button>
          </div>
        </Card>
      </div>

      {/* COLLAPSIBLE SHAP ANALYSIS PANEL */}
      <AnimatePresence>
        {showShapDetails && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: 'auto' }}
            exit={{ opacity: 0, height: 0 }}
            transition={{ duration: 0.3 }}
            className="overflow-hidden mt-6"
          >
            <Card className="p-6 bg-surface border border-subtle">
              <div className="mb-4">
                <h4 className="text-h4 text-primary flex items-center gap-2">
                  <HiOutlineChartBar className="text-brand-primary" />
                  Detailed Feature Attributions (SHAP Analysis)
                </h4>
                <p className="text-caption text-secondary mt-0.5">
                  Exact mathematical log-odds feature contributions computed via TreeExplainer.
                </p>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                {/* Positive SHAP */}
                <div>
                  <span className="text-caption text-red-400 font-semibold uppercase tracking-wider block mb-3">
                    Positive Risk Drivers (SHAP Log-Odds)
                  </span>
                  <div className="space-y-2">
                    {topPositiveShap.map((item, idx) => (
                      <div key={idx} className="p-3 rounded-lg bg-base/60 border border-subtle flex items-center justify-between text-xs">
                        <span className="text-primary font-medium">
                          {FEATURE_LABEL_MAP[item.feature] || item.feature}: <strong className="font-mono">{formatFeatureValue(item.feature, item.value)}</strong>
                        </span>
                        <span className="font-mono text-red-400 font-bold bg-red-500/10 px-2 py-0.5 rounded border border-red-500/20">
                          +{Number(item.shap_value).toFixed(3)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                {/* Negative SHAP */}
                <div>
                  <span className="text-caption text-green-400 font-semibold uppercase tracking-wider block mb-3">
                    Negative Risk Drivers (SHAP Log-Odds)
                  </span>
                  <div className="space-y-2">
                    {topNegativeShap.length === 0 ? (
                      <p className="text-caption text-muted italic">No negative drivers detected.</p>
                    ) : (
                      topNegativeShap.map((item, idx) => (
                        <div key={idx} className="p-3 rounded-lg bg-base/60 border border-subtle flex items-center justify-between text-xs">
                          <span className="text-primary font-medium">
                            {FEATURE_LABEL_MAP[item.feature] || item.feature}: <strong className="font-mono">{formatFeatureValue(item.feature, item.value)}</strong>
                          </span>
                          <span className="font-mono text-green-400 font-bold bg-green-500/10 px-2 py-0.5 rounded border border-green-500/20">
                            {Number(item.shap_value).toFixed(3)}
                          </span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              </div>
            </Card>
          </motion.div>
        )}
      </AnimatePresence>

      {/* XAI Disclaimer Note */}
      <div className="mt-4 text-caption text-muted flex items-start gap-2">
        <HiOutlineInformationCircle className="text-base shrink-0 mt-0.5 text-secondary" />
        <p>
          SHAP and LIME explain the behavior of the Machine Learning model. They cross-verify the prediction and do not replace the deterministic legal rule results. Raw values are preserved in the JSON download.
        </p>
      </div>
    </motion.section>
  );
}
