import { MapPin, Calendar, Sprout, ChevronRight } from 'lucide-react';
import type { FieldInfo } from '../types';

interface FieldCardProps {
  field: FieldInfo;
  onClick?: () => void;
}

export function FieldCard({ field, onClick }: FieldCardProps) {
  let badgeColor = 'bg-emerald-100 text-emerald-800 border-emerald-200';
  if (field.status.includes('ध्यान')) {
    badgeColor = 'bg-amber-100 text-amber-800 border-amber-200';
  }

  return (
    <div
      onClick={onClick}
      className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm hover:shadow-md transition cursor-pointer space-y-3"
    >
      <div className="flex items-start justify-between">
        <div>
          <h4 className="font-bold text-slate-800 text-sm">{field.name}</h4>
          <p className="text-xs text-slate-500 flex items-center gap-1 mt-0.5">
            <MapPin className="w-3.5 h-3.5 text-slate-400" />
            <span>{field.location}</span>
          </p>
        </div>
        <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full border ${badgeColor}`}>
          {field.status}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2 bg-slate-50 p-2.5 rounded-xl text-xs">
        <div className="flex items-center gap-1.5 text-slate-700">
          <Sprout className="w-4 h-4 text-emerald-600" />
          <span className="font-medium">{field.cropName}</span>
        </div>
        <div className="text-right font-semibold text-emerald-800">
          {field.areaAcres} एकड़ (Acres)
        </div>
      </div>

      <div className="flex items-center justify-between text-[11px] text-slate-400 border-t border-slate-100 pt-2">
        <span className="flex items-center gap-1">
          <Calendar className="w-3.5 h-3.5" />
          अंतिम जांच: {field.lastInspectionDate}
        </span>
        <span className="text-emerald-700 font-semibold flex items-center">
          विवरण देखें <ChevronRight className="w-3.5 h-3.5 ml-0.5" />
        </span>
      </div>
    </div>
  );
}
