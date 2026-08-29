import { twMerge } from 'tailwind-merge';

export default function Card({ children, accent, className }) {
  const normalizedAccent = accent?.toUpperCase();
  
  const borderAccent = 
    normalizedAccent === 'CRITICAL' ? 'border-t-4 border-t-red-500' :
    normalizedAccent === 'HIGH' ? 'border-t-4 border-t-orange-500' :
    normalizedAccent === 'MEDIUM' ? 'border-t-4 border-t-yellow-500' :
    normalizedAccent === 'LOW' ? 'border-t-4 border-t-green-500' :
    'border border-subtle';

  return (
    <div className={twMerge(
      'bg-surface rounded-xl shadow-card',
      borderAccent,
      className
    )}>
      {children}
    </div>
  );
}
