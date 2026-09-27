import { Camera, FlaskConical, Plane, Calendar } from 'lucide-react';
import type { FieldHistoryItem } from '../types';

interface HistoryCardProps {
  item: FieldHistoryItem;
}

export function HistoryCard({ item }: HistoryCardProps) {
  const getIcon = () => {
    switch (item.type) {
      case 'crop':
        return <Camera className="w-4 h-4 text-emerald-700" />;
      case 'soil':
        return <FlaskConical className="w-4 h-4 text-amber-700" />;
      case 'drone':
        return <Plane className="w-4 h-4 text-blue-700" />;
    }
  };

  return (
    <div className="bg-white rounded-xl p-3 border border-slate-200/80 flex items-center justify-between gap-3 text-xs shadow-2xs">
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center flex-shrink-0">
          {getIcon()}
        </div>
        <div>
          <h5 className="font-bold text-slate-800">{item.title}</h5>
          <p className="text-[11px] text-slate-500 mt-0.5">{item.summary}</p>
        </div>
      </div>

      <div className="text-right flex-shrink-0">
        <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-md font-medium">
          {item.statusBadge}
        </span>
        <div className="text-[10px] text-slate-400 mt-1 flex items-center gap-1 justify-end">
          <Calendar className="w-3 h-3" />
          {item.date}
        </div>
      </div>
    </div>
  );
}
