import { motion } from 'framer-motion';
import Card from '../ui/Card';
import Badge from '../ui/Badge';

export default function RemediationSection({ items }) {
  if (!items || items.length === 0) return null;

  return (
    <motion.section 
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.3 }}
      className="mb-8"
    >
      <Card className="overflow-hidden">
        <div className="p-6 border-b border-subtle">
          <h3 className="text-h3 text-primary">Remediation Priority Matrix</h3>
          <p className="text-caption text-secondary mt-1">Sorted by regulatory urgency and penalty exposure</p>
        </div>
        
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-base border-b border-subtle">
                <th className="px-6 py-4 text-label text-secondary">Priority</th>
                <th className="px-6 py-4 text-label text-secondary">Rule</th>
                <th className="px-6 py-4 text-label text-secondary">Action</th>
                <th className="px-6 py-4 text-label text-secondary">Urgency</th>
                <th className="px-6 py-4 text-label text-secondary text-right">Penalty</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item, index) => (
                <motion.tr 
                  key={item.rule_id}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.4 + (index * 0.05) }}
                  className={`border-b border-subtle hover:bg-elevated transition-colors ${index % 2 === 0 ? 'bg-surface' : 'bg-base/30'}`}
                >
                  <td className="px-6 py-4 font-bold text-primary">
                    #{item.priority}
                  </td>
                  <td className="px-6 py-4">
                    <div className="font-mono text-sm text-primary">{item.rule_id}</div>
                    <div className="text-xs text-secondary mt-1 truncate max-w-[200px]" title={item.rule_name}>{item.rule_name}</div>
                  </td>
                  <td className="px-6 py-4">
                    <div className="text-sm text-primary truncate max-w-[300px]" title={item.action}>
                      {item.action || "Review associated records and align with DPDP requirements."}
                    </div>
                  </td>
                  <td className="px-6 py-4">
                    <Badge severity={item.urgency} />
                  </td>
                  <td className="px-6 py-4 text-right">
                    <span className="text-sm font-medium text-primary">₹{item.penalty_exposure_crore} Cr</span>
                    <div className="w-full h-1 bg-elevated mt-2 rounded-full overflow-hidden">
                      <div 
                        className="h-full bg-red-500/50" 
                        style={{ width: `${Math.min((item.penalty_exposure_crore / 250) * 100, 100)}%` }} 
                      />
                    </div>
                  </td>
                </motion.tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>
    </motion.section>
  );
}
