import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { HiChevronDown } from 'react-icons/hi2';
import Card from '../ui/Card';
import Badge from '../ui/Badge';

function ViolationCard({ violation }) {
  const [isExpanded, setIsExpanded] = useState(false);
  const exp = violation.explanation;

  const getRootCauseLabel = (cause) => {
    switch (cause) {
      case 'PROCESS_GAP': return 'Process Gap';
      case 'TECHNICAL_GAP': return 'Technical Gap';
      case 'GOVERNANCE_GAP': return 'Governance Gap';
      case 'IMPLEMENTATION_GAP': return 'Implementation Gap';
      case 'HUMAN_ERROR': return 'Human Error';
      default: return cause || 'System Issue';
    }
  };

  // Safely get arrays and numbers from explanation
  const signals = Array.isArray(exp?.signals_analysis) ? exp.signals_analysis : [];
  const mitigationSteps = Array.isArray(exp?.mitigation) ? exp.mitigation : [];
  const totalSignalWeight = typeof exp?.total_signal_weight === 'number' 
    ? exp.total_signal_weight 
    : (typeof exp?.total_shap === 'number' ? exp.total_shap : 0);

  return (
    <Card
      accent={violation.severity}
      className={`mb-4 transition-all duration-300 ${isExpanded ? 'shadow-glow border-brand-primary/30' : ''}`}
    >
      {/* Header (Always Visible) */}
      <div
        className="p-5 cursor-pointer hover:bg-elevated/50 transition-colors flex items-center justify-between"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <div className="flex flex-col sm:flex-row sm:items-center gap-4 flex-1">
          <Badge severity={violation.severity} className="w-fit" />

          <div className="flex-1 min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="font-mono text-primary font-medium">{violation.rule_id}</span>
              <span className="text-primary truncate">{violation.rule_name}</span>
              <span className="text-caption text-muted italic hidden md:inline-block">({violation.dpdp_section})</span>
            </div>

            <div className="flex flex-wrap items-center gap-4 mt-2 text-sm">
              <span className="text-secondary bg-base px-2 py-0.5 rounded border border-subtle">
                <span className="text-primary font-medium">{violation.occurrence_count}</span> occurrences
              </span>
              <span className="text-secondary">
                Penalty: <span className="text-red-400 font-medium">₹{violation.penalty_exposure_crore} Cr</span>
              </span>
              <span className="text-secondary">
                Root Cause: <span className="text-primary font-medium">{getRootCauseLabel(violation.root_cause)}</span>
              </span>
            </div>
          </div>
        </div>

        <motion.div
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.3 }}
          className="p-2 text-secondary hover:text-primary hover:bg-elevated rounded-full ml-4 flex-shrink-0"
        >
          <HiChevronDown className="text-xl" />
        </motion.div>
      </div>

      {/* Expanded Content */}
      <AnimatePresence>
        {isExpanded && exp && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.3, ease: 'easeOut' }}
            className="overflow-hidden border-t border-subtle bg-base/30"
          >
            <div className="p-6 grid grid-cols-1 lg:grid-cols-5 gap-8">

              {/* LEFT COLUMN: Rule Signal Attribution (60%) */}
              <div className="lg:col-span-3">
                <h4 className="text-h4 text-primary mb-1">Rule Signal Attribution</h4>
                <p className="text-caption text-secondary mb-4">Deterministic heuristic signal weights evaluated for this violation</p>

                <div className="overflow-x-auto border border-subtle rounded-lg bg-surface">
                  <table className="w-full text-left">
                    <thead>
                      <tr className="border-b border-subtle bg-base">
                        <th className="px-4 py-2 text-label text-secondary font-medium">Signal</th>
                        <th className="px-4 py-2 text-label text-secondary font-medium">Description</th>
                        <th className="px-4 py-2 text-label text-secondary font-medium">Weight</th>
                        <th className="px-4 py-2 text-label text-secondary font-medium text-center">Fired</th>
                        <th className="px-4 py-2 text-label text-secondary font-medium">Reason</th>
                        <th className="px-4 py-2 text-label text-secondary font-medium text-right">Contribution</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-subtle">
                      {signals.map((sig, idx) => {
                        const contrib = sig?.signal_contribution ?? sig?.phi ?? 0;
                        return (
                          <tr key={idx} className={sig?.fired ? 'bg-brand-glow/10' : ''}>
                            <td className="px-4 py-3 font-mono text-sm font-bold text-primary">{sig?.signal || '—'}</td>
                            <td className="px-4 py-3 text-caption text-secondary">{sig?.description || '—'}</td>
                            <td className="px-4 py-3 text-sm text-primary relative min-w-[80px]">
                              <div className="relative z-10">{(sig?.weight ?? 0).toFixed(2)}</div>
                              <div
                                className="absolute inset-y-1 left-2 bg-blue-500/20 rounded z-0"
                                style={{ width: `${Math.min((sig?.weight ?? 0) * 100, 100)}%` }}
                              />
                            </td>
                            <td className="px-4 py-3 text-center">
                              {sig?.fired ? (
                                <span className="text-green-400 font-bold">✓</span>
                              ) : (
                                <span className="text-muted">—</span>
                              )}
                            </td>
                            <td className="px-4 py-3 text-xs italic text-secondary max-w-[200px] truncate" title={sig?.reason || ''}>
                              {sig?.fired ? (sig?.reason || '—') : '—'}
                            </td>
                            <td className="px-4 py-3 text-sm text-right font-mono">
                              {sig?.fired ? (
                                <span className="text-blue-400 font-bold">{contrib.toFixed(2)}</span>
                              ) : (
                                <span className="text-muted">0.00</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                      <tr className="bg-brand-primary/10 border-t border-brand-primary/30">
                        <td colSpan="5" className="px-4 py-3 text-sm text-primary text-right font-medium">Total Signal Weight:</td>
                        <td className="px-4 py-3 text-sm text-blue-400 text-right font-bold font-mono">
                          {totalSignalWeight.toFixed(2)}
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>
              </div>

              {/* RIGHT COLUMN: Explanation Text (40%) */}
              <div className="lg:col-span-2 space-y-5">
                <div>
                  <div className="text-label text-secondary mb-1">WHAT HAPPENED</div>
                  <p className="text-sm text-primary">{exp?.why_detected || 'Explanation not available'}</p>
                </div>

                <hr className="border-subtle" />

                <div>
                  <div className="text-label text-secondary mb-1">DPDP ACT VIOLATION</div>
                  <p className="text-sm text-secondary italic">{exp?.risk_reason || 'Regulation context not available'}</p>
                </div>

                <hr className="border-subtle" />

                <div>
                  <div className="text-label text-secondary mb-1">RECORD EVIDENCE</div>
                  <div className="text-xs font-mono text-primary bg-elevated p-3 rounded-md border border-subtle overflow-x-auto">
                    {exp?.evidence || 'No specific evidence extracted'}
                  </div>
                </div>

                <hr className="border-subtle" />

                <div>
                  <div className="text-label text-secondary mb-2">REMEDIATION STEPS</div>
                  <ul className="space-y-2">
                    {mitigationSteps.length > 0 ? (
                      mitigationSteps.map((step, i) => (
                        <li key={i} className="flex items-start gap-2 text-sm text-primary">
                          <span className="text-brand-primary font-medium">{i + 1}.</span>
                          <span className="leading-snug">{step}</span>
                        </li>
                      ))
                    ) : (
                      <li className="text-sm text-secondary">No remediation steps provided.</li>
                    )}
                  </ul>
                </div>
              </div>

            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </Card>
  );
}

export default function ViolationsSection({ violations }) {
  const [filter, setFilter] = useState('ALL');

  if (!violations || violations.length === 0) return null;

  const filteredViolations = filter === 'ALL'
    ? violations
    : violations.filter(v => v.severity === filter);

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.4 }}
      className="mb-12"
    >
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-6">
        <div>
          <div className="flex items-center gap-3">
            <h3 className="text-h2 text-primary">Violations Detected</h3>
            <span className="px-2.5 py-0.5 bg-elevated border border-subtle rounded-full text-xs font-bold text-primary">
              {violations.length} rules
            </span>
          </div>
        </div>

        {/* Filter Row */}
        <div className="flex flex-wrap gap-2">
          {['ALL', 'CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors border
                ${filter === f
                  ? 'bg-brand-primary border-brand-primary text-white'
                  : 'bg-transparent border-subtle text-secondary hover:text-primary hover:border-primary/30'}`}
            >
              {f}
            </button>
          ))}
        </div>
      </div>

      <div className="space-y-4">
        {filteredViolations.length === 0 ? (
          <div className="p-8 text-center bg-surface border border-subtle rounded-xl text-secondary">
            No violations match the selected filter.
          </div>
        ) : (
          filteredViolations.map((violation, idx) => (
            <motion.div
              key={violation.rule_id}
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4 + (idx * 0.05) }}
            >
              <ViolationCard violation={violation} index={idx} />
            </motion.div>
          ))
        )}
      </div>
    </motion.section>
  );
}
