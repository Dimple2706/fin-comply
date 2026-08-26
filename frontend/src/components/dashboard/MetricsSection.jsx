import { motion } from 'framer-motion';
import { PieChart, Pie, Cell, ResponsiveContainer } from 'recharts';
import {
  HiOutlineExclamationTriangle,
  HiOutlineCurrencyRupee
} from 'react-icons/hi2';

function CountUp({ value, suffix = '', prefix = '' }) {
  return (
    <span className="text-[36px] font-bold text-primary leading-none">
      {prefix}{value}{suffix}
    </span>
  );
}

export default function MetricsSection({ data }) {
  const {
    risk_score,
    risk_tier,
    total_violation_occurrences,
    unique_rules_violated,
    total_penalty_exposure_crore,
    total_obligations
  } = data;

  const scoreNum = Number(risk_score) || 0;

  // Temporary fallback until backend sends dynamic rule count.
  // Backend will be fixed next to supply this from PostgreSQL.
  const obligationCount = Number(total_obligations) || 19;

  const breachedPercentage =
    obligationCount > 0
      ? Math.min((unique_rules_violated / obligationCount) * 100, 100)
      : 0;

  const iR = 90;
  const oR = 120;

  const gaugeData = [
    { name: 'Low', value: 30, color: 'var(--low)' },
    { name: 'Medium', value: 25, color: 'var(--medium)' },
    { name: 'High', value: 20, color: 'var(--high)' },
    { name: 'Critical', value: 25, color: 'var(--critical)' },
  ];

  let glowClass =
    'border-t-green-500 shadow-[0_0_20px_rgba(34,197,94,0.1)]';

  if (risk_tier === 'MEDIUM') {
    glowClass =
      'border-t-yellow-500 shadow-[0_0_20px_rgba(234,179,8,0.1)]';
  }

  if (risk_tier === 'HIGH') {
    glowClass =
      'border-t-orange-500 shadow-[0_0_20px_rgba(249,115,22,0.1)]';
  }

  if (risk_tier === 'CRITICAL') {
    glowClass =
      'border-t-red-500 shadow-[0_0_20px_rgba(239,68,68,0.2)] animate-[pulse_3s_ease-in-out_infinite]';
  }

  return (
    <motion.section
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: 0.1 }}
      className="grid grid-cols-1 xl:grid-cols-5 gap-6 mb-8"
    >
      {/* LEFT: Risk Gauge */}
      <div
        className={`xl:col-span-2 bg-surface rounded-xl border border-subtle border-t-4 p-8 flex flex-col items-center justify-center relative ${glowClass}`}
      >
        <div className="h-[200px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                dataKey="value"
                startAngle={180}
                endAngle={0}
                data={gaugeData}
                cx="50%"
                cy="75%"
                innerRadius={iR}
                outerRadius={oR}
                stroke="none"
              >
                {gaugeData.map((entry, index) => (
                  <Cell
                    key={`cell-${index}`}
                    fill={entry.color}
                  />
                ))}
              </Pie>
            </PieChart>
          </ResponsiveContainer>
        </div>

        <div className="absolute top-[60%] text-center">
          <div className="flex items-baseline justify-center gap-1">
            <span className="text-[48px] font-bold text-primary leading-none">
              {scoreNum.toFixed(1)}
            </span>

            <span className="text-secondary font-medium">
              /100
            </span>
          </div>

          <div
            className={`inline-flex px-3 py-1 mt-2 rounded-full text-xs font-bold uppercase tracking-wider
              ${
                risk_tier === 'CRITICAL'
                  ? 'bg-red-500 text-white'
                  : risk_tier === 'HIGH'
                  ? 'bg-orange-500 text-white'
                  : risk_tier === 'MEDIUM'
                  ? 'bg-yellow-500 text-white'
                  : 'bg-green-500 text-white'
              }`}
          >
            {risk_tier} RISK
          </div>

          <div className="text-caption mt-2">
            ISO 31000 Risk Score
          </div>
        </div>
      </div>

      {/* RIGHT: Metric Cards */}
      <div className="xl:col-span-3 grid grid-cols-1 md:grid-cols-3 gap-6">

        {/* Violation occurrences */}
        <div className="bg-surface rounded-xl border border-subtle border-t-3 border-t-orange-500 p-5 pt-6 shadow-card flex flex-col justify-between">
          <div className="flex items-start justify-between mb-4">
            <CountUp value={total_violation_occurrences} />

            <HiOutlineExclamationTriangle className="text-2xl text-orange-500" />
          </div>

          <div className="text-sm font-medium text-secondary">
            Violation Occurrences Detected
          </div>
        </div>

        {/* Rules breached */}
        <div className="bg-surface rounded-xl border border-subtle border-t-3 border-t-blue-500 p-5 pt-6 shadow-card flex flex-col justify-between">

          <div className="mb-4">
            <CountUp value={unique_rules_violated} />
          </div>

          <div>
            <div className="text-sm font-medium text-secondary mb-3">
              of {obligationCount} Compliance Obligations Breached
            </div>

            <div className="w-full bg-elevated h-1.5 rounded-full overflow-hidden">
              <div
                className="h-full bg-blue-500 rounded-full transition-all duration-1000"
                style={{
                  width: `${breachedPercentage}%`
                }}
              />
            </div>
          </div>
        </div>

        {/* Penalty */}
        <div className="bg-surface rounded-xl border border-subtle border-t-3 border-t-red-500 p-5 pt-6 shadow-card flex flex-col justify-between">

          <div className="flex items-start justify-between mb-4">
            <CountUp
              value={total_penalty_exposure_crore}
              prefix="₹"
              suffix=" Cr"
            />

            <HiOutlineCurrencyRupee className="text-2xl text-red-500" />
          </div>

          <div className="text-sm font-medium text-secondary">
            Maximum Regulatory Penalty
          </div>
        </div>

      </div>
    </motion.section>
  );
}