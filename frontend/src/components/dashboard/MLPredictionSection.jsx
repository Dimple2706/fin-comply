import { motion } from 'framer-motion';
import { 
  HiOutlineCpuChip, 
  HiOutlineChartBar, 
  HiOutlineArrowTrendingUp, 
  HiOutlineArrowTrendingDown,
  HiOutlineCheckCircle,
  HiOutlineExclamationTriangle,
  HiOutlineInformationCircle
} from 'react-icons/hi2';
import Card from '../ui/Card';

const TIER_COLORS = {
  COMPLIANT: { bg: 'bg-green-500/10', text: 'text-green-400', border: 'border-green-500/30', fill: '#22c55e' },
  LOW: { bg: 'bg-blue-500/10', text: 'text-blue-400', border: 'border-blue-500/30', fill: '#3b82f6' },
  MEDIUM: { bg: 'bg-yellow-500/10', text: 'text-yellow-400', border: 'border-yellow-500/30', fill: '#eab308' },
  HIGH: { bg: 'bg-orange-500/10', text: 'text-orange-400', border: 'border-orange-500/30', fill: '#f97316' },
  CRITICAL: { bg: 'bg-red-500/10', text: 'text-red-400', border: 'border-red-500/30', fill: '#ef4444' },
};

const FEATURE_LABEL_MAP = {
  n_violations: 'Total Violations Count',
  n_warnings: 'Total Warnings Count',
  n_critical_rules_fired: 'Critical Rules Triggered',
  n_high_rules_fired: 'High Severity Rules Triggered',
  breach_rule_fired: 'Data Breach Detected (DPDP-014)',
  minor_data_rule_fired: "Children's Data Violation (DPDP-005)",
  max_rule_score: 'Max Rule Score Magnitude',
  max_prevalence_ratio: 'Max Prevalence Ratio',
  consent_violation_count: 'Consent Violations Count',
  retention_violation_count: 'Retention Violations Count',
  encryption_violation_count: 'Encryption Violations Count',
  access_violation_count: 'Unauthorized Access Count',
  policy_violation_count: 'Internal Policy Violations Count'
};

export default function MLPredictionSection({ mlData, deterministicTier, deterministicScore }) {
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
    model_metadata = {},
  } = mlData;
  const predStyle = TIER_COLORS[predicted_tier] || TIER_COLORS.MEDIUM;
  const detStyle = TIER_COLORS[deterministicTier] || TIER_COLORS.MEDIUM;

  const shapContributions = shap_explanation.feature_contributions || [];
  const topPositive = shapContributions
    .filter((item) => item.direction === 'positive')
    .slice(0, 3);
  const topNegative = shapContributions
    .filter((item) => item.direction === 'negative')
    .slice(0, 3);
  const limeContributions = (lime_explanation.feature_contributions || []).slice(0, 10);

  const rawConf = probabilities[predicted_tier] || 0;
  const confPct = rawConf > 1 ? rawConf : rawConf * 100;

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
              Explainable AI Risk Model
              <span className="px-2 py-0.5 rounded text-[11px] font-mono bg-brand-primary/10 text-brand-primary border border-brand-primary/20">
                XGBoost + SHAP + LIME
              </span>
            </h3>
            <p className="text-caption text-secondary">
              Independent machine learning verification trained with isolated cross-validation and strict holdout evaluation.
            </p>
          </div>
        </div>

        {model_metadata?.test_macro_f1 && (
          <div className="flex items-center gap-2 px-3 py-1 rounded-lg bg-elevated border border-subtle text-caption text-secondary">
            <span>Model Holdout Macro-F1:</span>
            <strong className="text-low font-mono">{model_metadata.test_macro_f1}</strong>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* CARD 1: Model Prediction & Tier Alignment (4 cols) */}
        <Card className="lg:col-span-4 p-6 bg-surface border border-subtle flex flex-col justify-between">
          <div>
            <h4 className="text-h4 text-primary mb-4 flex items-center gap-2">
              <HiOutlineChartBar className="text-brand-primary" />
              Risk Classification
            </h4>

            {/* Model Predicted Tier */}
            <div className={`p-4 rounded-xl border mb-4 ${predStyle.bg} ${predStyle.border}`}>
              <div className="text-caption text-secondary uppercase font-semibold tracking-wider">
                ML Predicted Tier
              </div>
              <div className={`text-2xl font-bold font-mono mt-1 ${predStyle.text}`}>
                {predicted_tier}
              </div>
              <div className="text-caption text-secondary mt-1">
                Prediction Confidence: <strong className="text-primary font-mono">{confPct.toFixed(1)}%</strong>
              </div>
            </div>

            {/* Deterministic Rule Engine Alignment */}
            <div className="p-4 rounded-xl border border-subtle bg-base/50">
              <div className="text-caption text-secondary uppercase font-semibold tracking-wider">
                Deterministic Rule Tier
              </div>
              <div className={`text-lg font-bold font-mono mt-0.5 ${detStyle.text}`}>
                {deterministicTier} (Score: {deterministicScore}/100)
              </div>
              <div className="text-caption text-secondary mt-1 flex items-center gap-1.5">
                {predicted_tier === deterministicTier ? (
                  <span className="text-low flex items-center gap-1">
                    <HiOutlineCheckCircle className="text-sm" /> 100% Tier Consensus
                  </span>
                ) : (
                  <span className="text-medium flex items-center gap-1">
                    <HiOutlineExclamationTriangle className="text-sm" /> Multi-Layer Variance
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Probabilities Distribution */}
          <div className="mt-6 pt-4 border-t border-subtle">
            <span className="text-caption text-secondary block mb-2 font-medium">
              Multi-Class Probability Distribution
            </span>
            <div className="space-y-2">
              {['COMPLIANT', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'].map((tier) => {
                const rawProb = probabilities[tier] || 0;
                const prob = rawProb > 1 ? rawProb : rawProb * 100;
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
          </div>
        </Card>

        {/* CARD 2: TreeSHAP Feature Attributions (8 cols) */}
        <Card className="lg:col-span-8 p-6 bg-surface border border-subtle">
          <div className="flex items-center justify-between mb-4">
            <div>
              <h4 className="text-h4 text-primary flex items-center gap-2">
                <HiOutlineArrowTrendingUp className="text-red-400" />
                TreeSHAP Feature Attributions
              </h4>
              <p className="text-caption text-secondary mt-0.5">
                Marginal feature contributions to log-odds output computed via Lundberg & Lee (2017) TreeExplainer.
              </p>
            </div>
          </div>

          {/* Top Risk Escalators (Positive SHAP) */}
          <div className="mb-6">
            <span className="text-caption text-red-400 font-semibold uppercase tracking-wider flex items-center gap-1 mb-3">
              <HiOutlineArrowTrendingUp className="text-base" />
              Key Risk Escalators (Positive Attribution)
            </span>
            {topPositive.length === 0 ? (
              <p className="text-caption text-muted italic">No strong risk escalating features detected.</p>
            ) : (
              <div className="space-y-2.5">
                {topPositive.map((item, idx) => (
                  <div key={idx} className="p-3 rounded-lg bg-base/60 border border-subtle flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-primary">
                        {FEATURE_LABEL_MAP[item.feature] || item.feature}
                      </span>
                      <span className="text-caption text-muted font-mono">
                        Feature Value: <strong className="text-secondary">{item.value}</strong>
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="px-2.5 py-1 rounded-md text-xs font-mono font-bold bg-red-500/10 text-red-400 border border-red-500/20">
                        +{Number(item.shap_value).toFixed(3)} SHAP
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Mitigating Factors (Negative SHAP) */}
          <div>
            <span className="text-caption text-green-400 font-semibold uppercase tracking-wider flex items-center gap-1 mb-3">
              <HiOutlineArrowTrendingDown className="text-base" />
              Mitigating Factors (Negative Attribution)
            </span>
            {topNegative.length === 0 ? (
              <p className="text-caption text-muted italic">No active mitigating factors detected.</p>
            ) : (
              <div className="space-y-2.5">
                {topNegative.map((item, idx) => (
                  <div key={idx} className="p-3 rounded-lg bg-base/60 border border-subtle flex items-center justify-between">
                    <div className="flex flex-col">
                      <span className="text-sm font-medium text-primary">
                        {FEATURE_LABEL_MAP[item.feature] || item.feature}
                      </span>
                      <span className="text-caption text-muted font-mono">
                        Feature Value: <strong className="text-secondary">{item.value}</strong>
                      </span>
                    </div>
                    <div className="text-right">
                      <span className="px-2.5 py-1 rounded-md text-xs font-mono font-bold bg-green-500/10 text-green-400 border border-green-500/20">
                        {Number(item.shap_value).toFixed(3)} SHAP
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      <Card className="mt-6 p-6 bg-surface border border-subtle">
        <div className="flex items-center justify-between gap-4 mb-4">
          <div>
            <h4 className="text-h4 text-primary flex items-center gap-2">
              <HiOutlineChartBar className="text-brand-primary" />
              LIME Local Explanation
            </h4>
            <p className="text-caption text-secondary mt-0.5">
              A local surrogate explanation showing which feature ranges pushed this individual prediction up or down.
            </p>
          </div>
          <span className="px-2.5 py-1 rounded-md text-xs font-mono bg-brand-primary/10 text-brand-primary border border-brand-primary/20">
            {lime_explanation.num_samples || 0} samples
          </span>
        </div>

        {limeContributions.length === 0 ? (
          <p className="text-caption text-muted italic">LIME explanation is unavailable for this prediction.</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            {limeContributions.map((item, idx) => {
              const positive = item.direction === 'positive';
              return (
                <div key={`${item.feature}-${idx}`} className="p-3 rounded-lg bg-base/60 border border-subtle flex items-center justify-between gap-4">
                  <div className="min-w-0">
                    <span className="text-sm font-medium text-primary block break-words">
                      {item.feature}
                    </span>
                    <span className="text-caption text-muted">
                      {positive ? 'Raises predicted risk' : 'Lowers predicted risk'}
                    </span>
                  </div>
                  <span className={`shrink-0 px-2.5 py-1 rounded-md text-xs font-mono font-bold border ${positive
                    ? 'bg-red-500/10 text-red-400 border-red-500/20'
                    : 'bg-green-500/10 text-green-400 border-green-500/20'
                  }`}>
                    {Number(item.coefficient).toFixed(4)}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </motion.section>
  );
}
