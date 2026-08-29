import { twMerge } from 'tailwind-merge';

export default function Skeleton({ className }) {
  return (
    <div className={twMerge(
      'animate-pulse bg-elevated rounded-md',
      className
    )} />
  );
}
