import { Bot, Camera, FlaskConical, LandPlot, Sun, Droplets, Wind, Sparkles, ChevronRight, Plus } from 'lucide-react';
import { useTranslation } from '../i18n/useTranslation';

interface HomeViewProps {
  onOpenAssistant: () => void;
  onOpenCropAnalysis: () => void;
  onOpenSoilAnalysis: () => void;
  onOpenDroneScan: () => void;
  onOpenFields: () => void;
}

export function HomeView({
  onOpenAssistant,
  onOpenCropAnalysis,
  onOpenSoilAnalysis,
  onOpenFields,
}: HomeViewProps) {
  const { t } = useTranslation();

  return (
    <div className="p-4 space-y-5 pb-8">
      {/* Welcome Banner */}
      <div className="bg-gradient-to-r from-emerald-800 to-emerald-900 text-white rounded-3xl p-5 shadow-lg relative overflow-hidden">
        <div className="relative z-10 space-y-1">
          <span className="text-xs font-semibold uppercase tracking-wider text-emerald-200 bg-white/10 px-2.5 py-1 rounded-full border border-white/10">
            {t('home.welcomeTag')}
          </span>
          <h2 className="text-2xl font-black pt-1">{t('home.welcome')}</h2>
          <p className="text-xs text-emerald-100 max-w-[90%] font-normal leading-relaxed">
            {t('home.subtitle')}
          </p>
        </div>
        <div className="absolute -right-4 -bottom-6 w-32 h-32 bg-emerald-600/30 rounded-full blur-2xl pointer-events-none" />
      </div>

      {/* PRIMARY ACTION CARD: "EarthMind से पूछें" */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
            {t('home.primaryActionTitle')}
          </span>
          <span className="text-[10px] text-emerald-700 font-bold bg-emerald-50 px-2 py-0.5 rounded-full border border-emerald-200">
            24x7 AI उपलब्ध
          </span>
        </div>

        <button
          onClick={onOpenAssistant}
          className="w-full bg-gradient-to-br from-emerald-700 via-emerald-800 to-teal-900 text-white rounded-3xl p-5 shadow-xl hover:shadow-2xl transition-all duration-300 transform active:scale-[0.99] text-left relative overflow-hidden group border border-emerald-600/40"
        >
          <div className="flex items-start justify-between">
            <div className="space-y-2 max-w-[80%]">
              <div className="inline-flex items-center gap-1.5 bg-white/15 px-3 py-1 rounded-full border border-white/20 backdrop-blur-md">
                <Bot className="w-4 h-4 text-emerald-300" />
                <span className="text-xs font-semibold text-emerald-100">AI सहायता केंद्र</span>
              </div>
              <h3 className="text-xl font-extrabold tracking-tight leading-snug">
                {t('home.askPrimary')}
              </h3>
              <p className="text-xs text-emerald-100 opacity-90 leading-relaxed">
                {t('home.askDesc')}
              </p>
            </div>

            <div className="w-12 h-12 rounded-2xl bg-white/20 backdrop-blur-md flex items-center justify-center text-white shadow-inner group-hover:scale-110 transition duration-300">
              <ChevronRight className="w-6 h-6" />
            </div>
          </div>

          <div className="mt-4 pt-3 border-t border-white/15 flex items-center justify-between text-xs text-emerald-100 font-medium">
            <span className="flex items-center gap-1">
              <Sparkles className="w-3.5 h-3.5 text-amber-300" />
              फसल रोग, खाद, सिंचाई और मौसम पूछें
            </span>
            <span className="bg-white/20 px-2 py-0.5 rounded-full text-[10px] flex items-center gap-1">
              <Plus className="w-3 h-3" /> टूल शामिल
            </span>
          </div>
        </button>
      </div>

      {/* SECONDARY ACTION CARDS: Compact rounded cards (Crop, Soil, My Fields). NO large Drone Scan card! */}
      <div className="space-y-2">
        <span className="text-xs font-bold text-slate-500 uppercase tracking-wider">
          {t('home.secondaryActionsTitle')}
        </span>

        <div className="grid grid-cols-3 gap-3">
          {/* Crop Analysis */}
          <button
            onClick={onOpenCropAnalysis}
            className="bg-white p-3.5 rounded-2xl border border-slate-200/90 shadow-sm hover:border-emerald-500 hover:shadow-md transition text-center flex flex-col items-center justify-center gap-2 group"
          >
            <div className="w-11 h-11 rounded-2xl bg-emerald-100 text-emerald-800 flex items-center justify-center group-hover:scale-105 transition">
              <Camera className="w-5 h-5" />
            </div>
            <span className="text-xs font-bold text-slate-800 line-clamp-1">अपनी फसल जाँचें</span>
          </button>

          {/* Soil Analysis */}
          <button
            onClick={onOpenSoilAnalysis}
            className="bg-white p-3.5 rounded-2xl border border-slate-200/90 shadow-sm hover:border-amber-500 hover:shadow-md transition text-center flex flex-col items-center justify-center gap-2 group"
          >
            <div className="w-11 h-11 rounded-2xl bg-amber-100 text-amber-900 flex items-center justify-center group-hover:scale-105 transition">
              <FlaskConical className="w-5 h-5" />
            </div>
            <span className="text-xs font-bold text-slate-800 line-clamp-1">मिट्टी जाँचें</span>
          </button>

          {/* My Fields */}
          <button
            onClick={onOpenFields}
            className="bg-white p-3.5 rounded-2xl border border-slate-200/90 shadow-sm hover:border-teal-500 hover:shadow-md transition text-center flex flex-col items-center justify-center gap-2 group"
          >
            <div className="w-11 h-11 rounded-2xl bg-teal-100 text-teal-900 flex items-center justify-center group-hover:scale-105 transition">
              <LandPlot className="w-5 h-5" />
            </div>
            <span className="text-xs font-bold text-slate-800 line-clamp-1">मेरे खेत</span>
          </button>
        </div>
      </div>

      {/* Weather Info Widget */}
      <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm space-y-3">
        <div className="flex items-center justify-between border-b border-slate-100 pb-2">
          <div className="flex items-center gap-2">
            <Sun className="w-5 h-5 text-amber-500" />
            <span className="font-bold text-slate-800 text-xs">समस्तीपुर, बिहार मौसम (Weather)</span>
          </div>
          <span className="text-[10px] bg-slate-100 text-slate-600 px-2 py-0.5 rounded-md font-medium">
            आज
          </span>
        </div>

        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <div className="p-2 bg-slate-50 rounded-xl">
            <span className="text-[10px] text-slate-400 block">तापमान</span>
            <span className="font-extrabold text-slate-800 text-sm">34°C</span>
          </div>
          <div className="p-2 bg-slate-50 rounded-xl">
            <span className="text-[10px] text-slate-400 block flex items-center justify-center gap-0.5">
              <Droplets className="w-3 h-3 text-blue-500" /> नमी
            </span>
            <span className="font-extrabold text-slate-800 text-sm">68%</span>
          </div>
          <div className="p-2 bg-slate-50 rounded-xl">
            <span className="text-[10px] text-slate-400 block flex items-center justify-center gap-0.5">
              <Wind className="w-3 h-3 text-teal-500" /> हवा
            </span>
            <span className="font-extrabold text-slate-800 text-sm">12 km/h</span>
          </div>
        </div>
      </div>

      {/* EarthMind Daily Farmer Recommendation Card */}
      <div className="bg-emerald-50 rounded-2xl p-4 border border-emerald-200/80 space-y-2">
        <div className="flex items-center gap-2 text-emerald-900 font-bold text-xs">
          <Sparkles className="w-4 h-4 text-emerald-700" />
          <span>EarthMind आज की सलाह (Daily Tip)</span>
        </div>
        <p className="text-xs text-emerald-800 leading-relaxed font-normal">
          धान की रोपाई से पूर्व खेत में ढैंचा (हरी खाद) पलटने से यूरिया की 25% बचत होगी और मिट्टी
          की संरचना में सुधार होगा।
        </p>
      </div>
    </div>
  );
}
