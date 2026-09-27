import { useState } from 'react';
import { FlaskConical, ArrowLeft, Bot, Sparkles, CheckCircle, Loader2 } from 'lucide-react';
import type { SoilAnalysisResult } from '../types';
import { soilAnalysisService } from '../services/soilAnalysisService';
import { UploadImageCard } from '../components/UploadImageCard';

interface SoilAnalysisViewProps {
  onOpenAssistant: () => void;
}

export function SoilAnalysisView({ onOpenAssistant }: SoilAnalysisViewProps) {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [phInput, setPhInput] = useState<number>(6.8);
  const [moistureInput, setMoistureInput] = useState<number>(65);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<SoilAnalysisResult | null>(null);

  const handleStartAnalysis = async () => {
    setIsAnalyzing(true);
    try {
      const res = await soilAnalysisService.analyzeSoil({
        imageFile: selectedImage || undefined,
        phInput,
        moistureInput,
      });
      setResult(res);
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="p-4 space-y-4 pb-12">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-slate-200 pb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={onOpenAssistant}
            className="p-1.5 rounded-full bg-slate-100 hover:bg-slate-200 text-slate-700 transition"
          >
            <ArrowLeft className="w-4 h-4" />
          </button>
          <div>
            <h3 className="font-bold text-slate-800 text-sm">मिट्टी जाँचें (Soil Analysis)</h3>
            <p className="text-[11px] text-slate-500">उर्वरता एवं pH स्वास्थ्य विश्लेषण</p>
          </div>
        </div>
        <div className="w-8 h-8 rounded-xl bg-amber-100 text-amber-900 flex items-center justify-center">
          <FlaskConical className="w-4 h-4" />
        </div>
      </div>

      {!result ? (
        <div className="space-y-4">
          <UploadImageCard
            title="मिट्टी या रिपोर्ट की फोटो लें (वैकल्पिक)"
            description="मिट्टी के रंग और बनावट का चित्र प्राथमिक अवलोकन में सहायता करता है।"
            onImageSelected={(img) => setSelectedImage(img)}
          />

          {/* Optional Soil Info Inputs */}
          <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm space-y-3">
            <h4 className="font-bold text-slate-800 text-xs">मिट्टी जानकारी दर्ज करें (Optional Details):</h4>

            <div className="space-y-2">
              <div className="flex justify-between text-xs font-semibold text-slate-700">
                <span>अनुमानित pH स्तर:</span>
                <span className="text-amber-700 font-bold">{phInput}</span>
              </div>
              <input
                type="range"
                min="5.0"
                max="8.5"
                step="0.1"
                value={phInput}
                onChange={(e) => setPhInput(parseFloat(e.target.value))}
                className="w-full accent-amber-600"
              />
            </div>

            <div className="space-y-2 pt-1">
              <div className="flex justify-between text-xs font-semibold text-slate-700">
                <span>नमी प्रतिशत (Moisture %):</span>
                <span className="text-blue-700 font-bold">{moistureInput}%</span>
              </div>
              <input
                type="range"
                min="20"
                max="90"
                step="1"
                value={moistureInput}
                onChange={(e) => setMoistureInput(parseInt(e.target.value))}
                className="w-full accent-blue-600"
              />
            </div>
          </div>

          <button
            onClick={handleStartAnalysis}
            disabled={isAnalyzing}
            className="w-full bg-amber-700 hover:bg-amber-800 text-white py-3.5 px-4 rounded-2xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 shadow-lg transition active:scale-98"
          >
            {isAnalyzing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>मिट्टी स्वास्थ्य विश्लेषित हो रहा है...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>मिट्टी जांच शुरू करें (Analyze Soil)</span>
              </>
            )}
          </button>
        </div>
      ) : (
        /* Soil Analysis Result */
        <div className="space-y-4 animate-in fade-in duration-300">
          <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <span className="text-xs font-bold text-slate-500 uppercase">{result.fieldName}</span>
              <span className="text-xs bg-emerald-100 text-emerald-800 font-bold px-2.5 py-0.5 rounded-full">
                स्वास्थ्य सूचकांक: {result.soilHealthIndex}/100
              </span>
            </div>

            {/* Metrics Grid */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-medium">pH मान (Acidity)</span>
                <span className="text-sm font-extrabold text-slate-800">{result.phLevel} (सामान्य)</span>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-medium">नमी प्रतिशत (Moisture)</span>
                <span className="text-sm font-extrabold text-slate-800">{result.moisturePercentage}%</span>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-medium">नाइट्रोजन (Nitrogen)</span>
                <span className="text-sm font-extrabold text-amber-700">{result.nitrogenLevel}</span>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-medium">फास्फोरस व पोटाश</span>
                <span className="text-sm font-extrabold text-emerald-700">{result.phosphorusLevel}</span>
              </div>
            </div>

            {/* Recommended Fertilizers */}
            <div className="space-y-2 pt-2 border-t border-slate-100">
              <span className="text-xs font-bold text-slate-700 block">अनुशंसित खाद एवं उर्वरक (Recommendations):</span>
              <ul className="space-y-1.5 text-xs text-slate-700">
                {result.recommendedFertilizer.map((rec, i) => (
                  <li key={i} className="flex items-start gap-2 bg-amber-50/70 p-2 rounded-xl text-amber-950 font-medium border border-amber-200/60">
                    <CheckCircle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                    <span>{rec}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          <button
            onClick={onOpenAssistant}
            className="w-full bg-emerald-800 hover:bg-emerald-900 text-white py-3 px-4 rounded-2xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 shadow-md transition"
          >
            <Bot className="w-4 h-4" />
            <span>EarthMind से और पूछें</span>
          </button>
        </div>
      )}
    </div>
  );
}
