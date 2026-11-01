import { motion } from 'framer-motion';

const formatEvaluatedDate = (iso) => {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? '—' : d.toLocaleDateString('en-GB');
};

export default function ExecutiveSummary({ summary, tenantId, evaluatedAt }) {
  return (
    <motion.section 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-surface border border-subtle border-l-4 border-l-brand-primary rounded-xl p-6 shadow-card mb-8 flex justify-between items-start gap-8"
    >
      <div className="flex-1">
        <h2 className="text-label text-brand-primary mb-3">COMPLIANCE ASSESSMENT SUMMARY</h2>
        <p className="text-body text-primary leading-relaxed max-w-4xl">
          {summary || 'No executive summary available.'}
        </p>
      </div>
      
      <div className="text-right flex-shrink-0 hidden md:block">
        <div className="text-caption text-muted font-mono mb-1">ID: REP-{(tenantId || '').toUpperCase()}</div>
        <div className="text-caption text-muted">Evaluated: {formatEvaluatedDate(evaluatedAt)}</div>
      </div>
    </motion.section>
  );
}
