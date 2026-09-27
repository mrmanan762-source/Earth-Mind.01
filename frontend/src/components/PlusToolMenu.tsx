import { Camera, FlaskConical, Plane, LandPlot, X } from 'lucide-react';
import { useTranslation } from '../i18n/useTranslation';

interface PlusToolMenuProps {
  isOpen: boolean;
  onClose: () => void;
  onSelectCropAnalysis: () => void;
  onSelectSoilAnalysis: () => void;
  onSelectDroneScan: () => void;
  onSelectMyFields: () => void;
}

export function PlusToolMenu({
  isOpen,
  onClose,
  onSelectCropAnalysis,
  onSelectSoilAnalysis,
  onSelectDroneScan,
  onSelectMyFields,
}: PlusToolMenuProps) {
  const { t } = useTranslation();

  if (!isOpen) return null;

  const tools = [
    {
      id: 'crop',
      label: t('tools.cropAnalysis'),
      desc: t('tools.cropAnalysisDesc'),
      icon: Camera,
      color: 'bg-emerald-100 text-emerald-800 border-emerald-200',
      action: () => {
        onSelectCropAnalysis();
        onClose();
      },
    },
    {
      id: 'soil',
      label: t('tools.soilAnalysis'),
      desc: t('tools.soilAnalysisDesc'),
      icon: FlaskConical,
      color: 'bg-amber-100 text-amber-900 border-amber-200',
      action: () => {
        onSelectSoilAnalysis();
        onClose();
      },
    },
    {
      id: 'drone',
      label: t('tools.droneScan'),
      desc: t('tools.droneScanDesc'),
      icon: Plane,
      color: 'bg-blue-100 text-blue-900 border-blue-200',
      action: () => {
        onSelectDroneScan();
        onClose();
      },
    },
    {
      id: 'fields',
      label: t('tools.myFields'),
      desc: t('tools.myFieldsDesc'),
      icon: LandPlot,
      color: 'bg-teal-100 text-teal-900 border-teal-200',
      action: () => {
        onSelectMyFields();
        onClose();
      },
    },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-end justify-center p-0 sm:p-4 animate-in fade-in duration-200">
      <div className="bg-white w-full max-w-md rounded-t-3xl sm:rounded-3xl shadow-2xl p-4 sm:p-5 flex flex-col gap-3">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-100">
          <div>
            <h3 className="font-bold text-slate-800 text-base">EarthMind टूल और सुविधाएं</h3>
            <p className="text-xs text-slate-500">आपकी कृषि सहायता के लिए टूल चुनें</p>
          </div>
          <button
            onClick={onClose}
            className="p-1.5 rounded-full bg-slate-100 text-slate-600 hover:bg-slate-200 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Tools Grid */}
        <div className="grid grid-cols-2 gap-3 pt-1">
          {tools.map((tool) => {
            const Icon = tool.icon;
            return (
              <button
                key={tool.id}
                onClick={tool.action}
                className={`p-3.5 rounded-2xl border text-left flex flex-col gap-2 transition-all hover:scale-[1.02] active:scale-[0.98] shadow-sm ${tool.color}`}
              >
                <div className="w-9 h-9 rounded-xl bg-white/80 backdrop-blur-sm flex items-center justify-center shadow-xs">
                  <Icon className="w-5 h-5" />
                </div>
                <div>
                  <div className="font-bold text-xs">{tool.label}</div>
                  <div className="text-[10px] opacity-80 mt-0.5 line-clamp-1">{tool.desc}</div>
                </div>
              </button>
            );
          })}
        </div>

        <div className="text-[11px] text-center text-slate-400 pt-1">
          ड्रोन जाँच अब सीधे + टूल मेनू से उपलब्ध है।
        </div>
      </div>
    </div>
  );
}
