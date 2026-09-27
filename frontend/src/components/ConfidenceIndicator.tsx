import { ShieldCheck } from 'lucide-react';

interface ConfidenceIndicatorProps {
  score: number;
}

export function ConfidenceIndicator({ score }: ConfidenceIndicatorProps) {
  let color = 'bg-emerald-100 text-emerald-800 border-emerald-300';
  if (score < 80) {
    color = 'bg-amber-100 text-amber-800 border-amber-300';
  } else if (score < 60) {
    color = 'bg-red-100 text-red-800 border-red-300';
  }

  return (
    <div
      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold border ${color}`}
    >
      <ShieldCheck className="w-3.5 h-3.5" />
      <span>EarthMind आत्मविश्वास: {score}%</span>
    </div>
  );
}
