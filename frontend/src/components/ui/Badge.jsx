import { twMerge } from 'tailwind-merge';

export default function Badge({ severity, label, className }) {
  const normalized = severity?.toUpperCase() || 'INFO';
  
  const baseClasses = 'inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border';
  
  const severityMap = {
    CRITICAL: {
      colors: 'bg-red-500/10 text-red-400 border-red-500/20',
      dot: 'bg-red-500'
    },
    HIGH: {
      colors: 'bg-orange-500/10 text-orange-400 border-orange-500/20',
      dot: 'bg-orange-500'
    },
    MEDIUM: {
      colors: 'bg-yellow-500/10 text-yellow-400 border-yellow-500/20',
      dot: 'bg-yellow-500'
    },
    LOW: {
      colors: 'bg-green-500/10 text-green-400 border-green-500/20',
      dot: 'bg-green-500'
    },
    INFO: {
      colors: 'bg-blue-500/10 text-blue-400 border-blue-500/20',
      dot: 'bg-blue-500'
    }
  };

  const config = severityMap[normalized] || severityMap.INFO;

  return (
    <span className={twMerge(baseClasses, config.colors, className)}>
      {normalized === 'CRITICAL' ? (
        <span className="relative flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-75 ${config.dot}`}></span>
          <span className={`relative inline-flex rounded-full h-2 w-2 ${config.dot}`}></span>
        </span>
      ) : (
        <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
      )}
      {label || normalized}
    </span>
  );
}
