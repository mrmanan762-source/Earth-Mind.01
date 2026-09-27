import { useState, useEffect } from 'react';
import { LandPlot, Plus, History } from 'lucide-react';
import type { FieldInfo, FieldHistoryItem } from '../types';
import { fieldService } from '../services/fieldService';
import { MOCK_FIELD_HISTORY } from '../mock/data';
import { FieldCard } from '../components/FieldCard';
import { HistoryCard } from '../components/HistoryCard';

interface FieldsViewProps {
  onOpenCropAnalysis: () => void;
  onOpenSoilAnalysis: () => void;
  onOpenDroneScan: () => void;
}

export function FieldsView({
  onOpenCropAnalysis,
}: FieldsViewProps) {
  const [fields, setFields] = useState<FieldInfo[]>([]);
  const [history] = useState<FieldHistoryItem[]>(MOCK_FIELD_HISTORY);

  useEffect(() => {
    fieldService.getFields().then((f) => setFields(f));
  }, []);

  return (
    <div className="p-4 space-y-5 pb-12">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div>
          <h3 className="font-bold text-slate-800 text-sm">मेरे खेत (My Fields)</h3>
          <p className="text-[11px] text-slate-500">पंजीकृत खेत एवं निरीक्षण इतिहास</p>
        </div>
        <button
          onClick={onOpenCropAnalysis}
          className="flex items-center gap-1 bg-emerald-700 hover:bg-emerald-800 text-white text-xs font-bold px-3 py-1.5 rounded-xl transition shadow-sm"
        >
          <Plus className="w-4 h-4" />
          <span>जाँच जोड़ें</span>
        </button>
      </div>

      {/* Fields List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
            <LandPlot className="w-3.5 h-3.5 text-slate-400" /> पंजीकृत खेत ({fields.length})
          </span>
        </div>

        <div className="space-y-3">
          {fields.map((field) => (
            <FieldCard key={field.id} field={field} onClick={onOpenCropAnalysis} />
          ))}
        </div>
      </div>

      {/* Recent History */}
      <div className="space-y-3 pt-2">
        <span className="text-xs font-bold text-slate-500 uppercase tracking-wider flex items-center gap-1">
          <History className="w-3.5 h-3.5 text-slate-400" /> हालिया निरीक्षण इतिहास (Recent Scans)
        </span>

        <div className="space-y-2">
          {history.map((item) => (
            <HistoryCard key={item.id} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}
