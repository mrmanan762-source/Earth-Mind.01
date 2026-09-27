import { CheckCircle2, Loader2 } from 'lucide-react';
import type { DroneScanProgress } from '../types';

interface ProgressStepperProps {
  steps: DroneScanProgress[];
  currentPercent: number;
}

export function ProgressStepper({ steps, currentPercent }: ProgressStepperProps) {
  return (
    <div className="w-full space-y-4">
      {/* Overall Bar */}
      <div>
        <div className="flex justify-between text-xs font-semibold text-slate-700 mb-1.5">
          <span>ड्रोन स्कैन प्रगति (Scan Progress)</span>
          <span className="text-emerald-700 font-bold">{currentPercent}%</span>
        </div>
        <div className="w-full bg-slate-200 h-2.5 rounded-full overflow-hidden">
          <div
            className="bg-emerald-600 h-2.5 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${currentPercent}%` }}
          />
        </div>
      </div>

      {/* Steps List */}
      <div className="space-y-2.5 pt-2">
        {steps.map((step, idx) => {
          const isDone = currentPercent >= step.percent;
          const isCurrent =
            currentPercent < step.percent &&
            (idx === 0 || currentPercent >= steps[idx - 1].percent);

          return (
            <div
              key={idx}
              className={`flex items-center gap-3 p-2.5 rounded-xl border text-xs transition-all ${
                isDone
                  ? 'bg-emerald-50 border-emerald-200 text-emerald-900 font-medium'
                  : isCurrent
                  ? 'bg-amber-50 border-amber-300 text-amber-900 font-semibold ring-1 ring-amber-300/50'
                  : 'bg-slate-50 border-slate-200 text-slate-400'
              }`}
            >
              {isDone ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              ) : isCurrent ? (
                <Loader2 className="w-4 h-4 text-amber-600 animate-spin flex-shrink-0" />
              ) : (
                <div className="w-4 h-4 rounded-full border-2 border-slate-300 flex-shrink-0" />
              )}
              <span className="flex-1">{step.title}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
