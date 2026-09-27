import { Sparkles } from 'lucide-react';

interface SuggestedQuestionProps {
  text: string;
  onClick: () => void;
}

export function SuggestedQuestion({ text, onClick }: SuggestedQuestionProps) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-2 bg-white hover:bg-emerald-50 text-slate-700 hover:text-emerald-900 border border-slate-200 hover:border-emerald-300 px-3 py-2 rounded-xl text-xs font-medium transition shadow-2xs text-left"
    >
      <Sparkles className="w-3.5 h-3.5 text-emerald-600 flex-shrink-0" />
      <span className="line-clamp-1">{text}</span>
    </button>
  );
}
