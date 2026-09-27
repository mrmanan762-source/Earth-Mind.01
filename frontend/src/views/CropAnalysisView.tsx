import { useState } from 'react';
import { Camera, ArrowLeft, Bot, AlertTriangle, CheckCircle, Sparkles, Loader2 } from 'lucide-react';
import type { CropAnalysisResult } from '../types';
import { cropAnalysisService } from '../services/cropAnalysisService';
import { ConfidenceIndicator } from '../components/ConfidenceIndicator';
import { UploadImageCard } from '../components/UploadImageCard';

interface CropAnalysisViewProps {
  onOpenAssistant: () => void;
}

export function CropAnalysisView({ onOpenAssistant }: CropAnalysisViewProps) {
  const [selectedImage, setSelectedImage] = useState<string | null>(null);
  const [selectedField, setSelectedField] = useState('field-1');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [result, setResult] = useState<CropAnalysisResult | null>(null);

  const handleStartAnalysis = async () => {
    if (!selectedImage) return;
    setIsAnalyzing(true);
    try {
      const res = await cropAnalysisService.analyzeCrop({
        imageFile: selectedImage,
        fieldId: selectedField,
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
            <h3 className="font-bold text-slate-800 text-sm">अपनी फसल जाँचें (Crop Analysis)</h3>
            <p className="text-[11px] text-slate-500">AI द्वारा रोग एवं कीट निदान</p>
          </div>
        </div>
        <div className="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center">
          <Camera className="w-4 h-4" />
        </div>
      </div>

      {!result ? (
        <div className="space-y-4">
          {/* Field Selector */}
          <div className="bg-white rounded-2xl p-3.5 border border-slate-200 shadow-sm space-y-2">
            <label className="text-xs font-bold text-slate-700 block">खेत चुनें (Select Field):</label>
            <select
              value={selectedField}
              onChange={(e) => setSelectedField(e.target.value)}
              className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-xs text-slate-800 font-medium focus:ring-2 focus:ring-emerald-600 focus:outline-none"
            >
              <option value="field-1">खेत 1 (उत्तर दिशा) - धान</option>
              <option value="field-2">खेत 2 (नदी पास) - मक्का</option>
            </select>
          </div>

          {/* Upload Image Component */}
          <UploadImageCard
            title="फसल की स्पष्ट फोटो लें या अपलोड करें"
            description="प्रभावित पत्ती या फल का नज़दीकी चित्र सबसे सटीक परिणाम देता है।"
            onImageSelected={(img) => setSelectedImage(img)}
          />

          {/* Action Button */}
          <button
            onClick={handleStartAnalysis}
            disabled={!selectedImage || isAnalyzing}
            className={`w-full py-3.5 px-4 rounded-2xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 shadow-lg transition ${
              selectedImage && !isAnalyzing
                ? 'bg-emerald-700 hover:bg-emerald-800 text-white active:scale-98'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            {isAnalyzing ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>AI विश्लेषण जारी है...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>फसल जाँच शुरू करें (Analyze Crop)</span>
              </>
            )}
          </button>
        </div>
      ) : (
        /* Result Screen */
        <div className="space-y-4 animate-in fade-in duration-300">
          {/* Captured Image Preview */}
          <div className="relative rounded-2xl overflow-hidden border border-slate-200 shadow-sm max-h-48">
            <img src={result.imageUrl} alt={result.cropName} className="w-full h-48 object-cover" />
            <div className="absolute top-2 left-2 bg-slate-900/80 text-white text-[10px] px-2.5 py-1 rounded-full backdrop-blur-sm font-semibold">
              {result.cropName}
            </div>
            <div className="absolute bottom-2 right-2">
              <ConfidenceIndicator score={result.confidence} />
            </div>
          </div>

          {/* Condition & Diagnosis Card */}
          <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <span className="text-xs font-bold text-slate-500 uppercase">निदान पूर्ण (Analysis Complete)</span>
              <span className="text-[11px] bg-amber-100 text-amber-900 font-bold px-2.5 py-0.5 rounded-full border border-amber-300">
                {result.condition}
              </span>
            </div>

            <div>
              <span className="text-[11px] text-slate-400 font-medium block">पहचाना गया रोग / कीट:</span>
              <h4 className="text-sm font-black text-slate-800 mt-0.5 flex items-start gap-1.5">
                <AlertTriangle className="w-4 h-4 text-amber-600 flex-shrink-0 mt-0.5" />
                {result.suspectedIssue}
              </h4>
            </div>

            {/* Recommended Treatments */}
            <div className="space-y-1.5 pt-2 border-t border-slate-100">
              <span className="text-xs font-bold text-slate-700 block">अनुशंसित उपचार (Recommended Actions):</span>
              <ul className="space-y-1.5 text-xs text-slate-700">
                {result.recommendedActions.map((act, i) => (
                  <li key={i} className="flex items-start gap-2 bg-emerald-50/60 p-2 rounded-xl text-emerald-950 font-medium">
                    <CheckCircle className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />
                    <span>{act}</span>
                  </li>
                ))}
              </ul>
            </div>

            {/* Follow-up Action */}
            <div className="space-y-1.5 pt-2 border-t border-slate-100">
              <span className="text-[11px] font-bold text-slate-500 block">आगे की कार्रवाई (Follow-up):</span>
              <ul className="space-y-1 text-xs text-slate-600">
                {result.followUpActions.map((f, idx) => (
                  <li key={idx} className="flex items-center gap-1.5">
                    <span className="w-1.5 h-1.5 bg-emerald-600 rounded-full" />
                    <span>{f}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>

          {/* Action Footer Button */}
          <button
            onClick={onOpenAssistant}
            className="w-full bg-emerald-800 hover:bg-emerald-900 text-white py-3 px-4 rounded-2xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 shadow-md transition"
          >
            <Bot className="w-4 h-4" />
            <span>EarthMind से और पूछें (Ask AI Companion)</span>
          </button>
        </div>
      )}
    </div>
  );
}
