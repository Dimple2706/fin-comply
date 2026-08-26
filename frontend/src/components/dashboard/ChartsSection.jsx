import { motion } from 'framer-motion';
import { PieChart, Pie, Cell, Tooltip as RechartsTooltip, BarChart, Bar, XAxis, YAxis, ResponsiveContainer } from 'recharts';
import Card from '../ui/Card';

const AGENT_COLORS = {
  regulation_agent: 'var(--brand-primary)', // blue
  audit_agent: 'var(--brand-secondary)',    // indigo
  risk_agent: '#8B5CF6'                     // violet
};

const SEVERITY_COLORS = {
  CRITICAL: 'var(--critical)',
  HIGH: 'var(--high)',
  MEDIUM: 'var(--medium)',
  LOW: 'var(--low)'
};

const CustomDonutTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="bg-elevated border border-subtle p-3 rounded-lg shadow-card">
        <p className="text-sm font-medium text-white mb-2">{data.name}</p>
        <div className="flex justify-between gap-4 text-xs">
          <span className="text-secondary">Violations:</span>
          <span className="font-mono text-red-400">{data.value}</span>
        </div>
        <div className="flex justify-between gap-4 text-xs mt-1">
          <span className="text-secondary">Warnings:</span>
          <span className="font-mono text-yellow-400">{data.warnings}</span>
        </div>
      </div>
    );
  }
  return null;
};

const CustomBarTooltip = ({ active, payload }) => {
  if (active && payload && payload.length) {
    const data = payload[0].payload;
    return (
      <div className="bg-elevated border border-subtle p-3 rounded-lg shadow-card max-w-[240px]">
        <p className="text-sm font-mono text-white">{data.rule}</p>
        <p className="text-xs text-secondary mt-1 mb-3 leading-snug">{data.name}</p>
        <div className="flex justify-between items-center gap-4">
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold bg-${data.severity.toLowerCase()}/10 text-${data.severity.toLowerCase()} border border-${data.severity.toLowerCase()}/20`}>
            {data.severity}
          </span>
          <span className="font-mono text-white text-sm">{data.contribution.toFixed(4)}</span>
        </div>
      </div>
    );
  }
  return null;
};

export default function ChartsSection({ breakdown, contributions, violations }) {
  // Agent Donut Data
  const donutData = Object.entries(breakdown || {})
    .map(([key, data]) => ({
      name: key.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase()),
      rawName: key,
      value: data.violations || 0,
      warnings: data.warnings || 0
    }))
    .filter(item => item.value > 0 || item.warnings > 0);

  const totalAgentViolations = donutData.reduce((acc, curr) => acc + curr.value, 0);

  // Risk Contribution Data
  const barData = Object.entries(contributions || {})
    .map(([ruleId, contribution]) => {
      const violation = (violations || []).find(v => v.rule_id === ruleId);
      return {
        rule: ruleId,
        name: violation ? violation.rule_name : ruleId,
        contribution: contribution,
        severity: violation ? violation.severity : 'LOW'
      };
    })
    .sort((a, b) => b.contribution - a.contribution);

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.2 }}
      className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8"
    >
      {/* LEFT: Agent Breakdown */}
      <Card className="p-6">
        <h3 className="text-h3 text-primary">Agent Analysis</h3>
        <div className="h-[240px] relative mt-4">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={donutData}
                cx="50%"
                cy="50%"
                innerRadius={70}
                outerRadius={100}
                paddingAngle={4}
                dataKey="value"
                stroke="none"
              >
                {donutData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={AGENT_COLORS[entry.rawName] || '#fff'} />
                ))}
              </Pie>
              <RechartsTooltip content={<CustomDonutTooltip />} cursor={{ fill: 'transparent' }} />
            </PieChart>
          </ResponsiveContainer>
          <div className="absolute inset-0 flex flex-col items-center justify-center pointer-events-none">
            <span className="text-3xl font-bold text-primary">{totalAgentViolations}</span>
            <span className="text-caption text-secondary">Total</span>
          </div>
        </div>
        <div className="mt-6 space-y-3">
          {donutData.map((agent) => (
            <div key={agent.name} className="flex items-center justify-between text-sm">
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: AGENT_COLORS[agent.rawName] }} />
                <span className="text-primary">{agent.name}</span>
              </div>
              <div className="flex gap-4 font-mono text-xs">
                <span className="text-red-400" title="Violations">{agent.value} V</span>
                <span className="text-yellow-400" title="Warnings">{agent.warnings} W</span>
              </div>
            </div>
          ))}
        </div>
      </Card>

      {/* RIGHT: Risk Contribution */}
      <Card className="p-6">
        <h3 className="text-h3 text-primary">Rule Risk Contributions</h3>
        <p className="text-caption text-secondary mt-1 mb-6">Contribution to overall risk score per rule</p>
        <div className="h-[300px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={barData}
              margin={{ top: 0, right: 30, left: 20, bottom: 0 }}
            >
              <XAxis type="number" domain={[0, 1]} hide />
              <YAxis
                type="category"
                dataKey="rule"
                axisLine={false}
                tickLine={false}
                tick={{ fill: 'var(--text-secondary)', fontSize: 12, fontFamily: 'monospace' }}
                width={80}
              />
              <RechartsTooltip content={<CustomBarTooltip />} cursor={{ fill: 'var(--bg-elevated)' }} />
              <Bar
                dataKey="contribution"
                radius={[0, 4, 4, 0]}
                animationDuration={1000}
              >
                {barData.map((entry, index) => (
                  <Cell key={`cell-${index}`} fill={SEVERITY_COLORS[entry.severity] || SEVERITY_COLORS.LOW} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </Card>
    </motion.section>
  );
}
