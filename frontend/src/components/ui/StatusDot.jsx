
export default function StatusDot({ status = 'active' }) {
  if (status === 'active') {
    return (
      <span className="relative flex h-2.5 w-2.5">
        <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-green-400 opacity-75"></span>
        <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-green-500"></span>
      </span>
    );
  }
  
  return <span className="h-2.5 w-2.5 rounded-full bg-red-500" />;
}
