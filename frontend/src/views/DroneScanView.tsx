import { useState } from 'react';
import { Plane, ArrowLeft, Bot, Sparkles, CheckCircle2, AlertCircle } from 'lucide-react';
import type { DroneScanProgress, DroneScanResult } from '../types';
import { droneScanService } from '../services/droneScanService';
import { ProgressStepper } from '../components/ProgressStepper';

interface DroneScanViewProps {
  onOpenAssistant: () => void;
  onOpenFields: () => void;
}

export function DroneScanView({ onOpenAssistant, onOpenFields }: DroneScanViewProps) {
  const [selectedField, setSelectedField] = useState('field-1');
  const [imagesCount, setImagesCount] = useState(4);
  const [isScanning, setIsScanning] = useState(false);
  const [scanPercent, setScanPercent] = useState(0);
  const [progressSteps, setProgressSteps] = useState<DroneScanProgress[]>([
    { title: 'तस्वीरें (Drone Imagery)', percent: 20, isComplete: false },
    { title: 'फसल स्वास्थ्य (Crop Health Mapping)', percent: 45, isComplete: false },
    { title: 'मिट्टी नमी (Soil Moisture Stress)', percent: 70, isComplete: false },
    { title: 'मौसम डेटा (Weather Data)', percent: 85, isComplete: false },
    { title: 'AI विश्लेषण (EarthMind AI Analysis)', percent: 100, isComplete: false },
  ]);
  const [scanResult, setScanResult] = useState<DroneScanResult | null>(null);

  const handleStartScan = async () => {
    setIsScanning(true);
    setScanResult(null);
    setScanPercent(10);

    try {
      const result = await droneScanService.startScan(
        { fieldId: selectedField },
        (progress) => {
          setScanPercent(progress.percent);
          setProgressSteps((prev) =>
            prev.map((p) =>
              p.percent <= progress.percent ? { ...p, isComplete: true } : p
            )
          );
        }
      );
      setScanResult(result);
    } finally {
      setIsScanning(false);
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
            <h3 className="font-bold text-slate-800 text-sm">ड्रोन जाँच (Drone Scan)</h3>
            <p className="text-[11px] text-slate-500">एरियल ड्रोन मैपिंग व खेत स्वास्थ्य विश्लेषण</p>
          </div>
        </div>
        <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-900 flex items-center justify-center">
          <Plane className="w-4 h-4" />
        </div>
      </div>

      {!scanResult && !isScanning ? (
        /* Configuration Form */
        <div className="space-y-4">
          <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm space-y-3">
            <div>
              <label className="text-xs font-bold text-slate-700 block mb-1">खेत चुनें (Select Field):</label>
              <select
                value={selectedField}
                onChange={(e) => setSelectedField(e.target.value)}
                className="w-full bg-slate-50 border border-slate-200 rounded-xl p-2.5 text-xs text-slate-800 font-medium focus:ring-2 focus:ring-blue-600 focus:outline-none"
              >
                <option value="field-1">खेत 1 (उत्तर दिशा) - 3.0 एकड़</option>
                <option value="field-2">खेत 2 (नदी पास) - 2.5 एकड़</option>
              </select>
            </div>

            <div>
              <label className="text-xs font-bold text-slate-700 block mb-1">ड्रोन फोटो अपलोड संख्या:</label>
              <div className="flex items-center gap-2">
                {[2, 4, 8, 12].map((num) => (
                  <button
                    key={num}
                    type="button"
                    onClick={() => setImagesCount(num)}
                    className={`flex-1 py-2 rounded-xl text-xs font-bold border transition ${
                      imagesCount === num
                        ? 'border-blue-600 bg-blue-50 text-blue-900 ring-2 ring-blue-600/30'
                        : 'border-slate-200 bg-slate-50 text-slate-600'
                    }`}
                  >
                    {num} तस्वीरें
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className="bg-blue-50/70 p-3.5 rounded-2xl border border-blue-200/80 text-xs text-blue-950 space-y-1">
            <span className="font-bold block flex items-center gap-1">
              <Sparkles className="w-3.5 h-3.5 text-blue-600" />
              ड्रोन स्कैन की विशेषताएं:
            </span>
            <p className="text-[11px] opacity-90 leading-relaxed">
              ड्रोन स्कैन संपूर्ण खेत का 3D एरियल नक्शा, नमी तनाव, कीट संक्रमण क्षेत्र और NDVI सूचकांक
              एक साथ विश्लेषित करता है।
            </p>
          </div>

          <button
            onClick={handleStartScan}
            className="w-full bg-blue-700 hover:bg-blue-800 text-white py-3.5 px-4 rounded-2xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 shadow-lg transition active:scale-98"
          >
            <Plane className="w-4 h-4" />
            <span>ड्रोन स्कैन शुरू करें (Start Drone Scan)</span>
          </button>
        </div>
      ) : isScanning ? (
        /* Progress Stepper View */
        <div className="bg-white rounded-2xl p-5 border border-slate-200 shadow-sm space-y-4 animate-in fade-in">
          <div className="text-center space-y-1">
            <div className="w-12 h-12 bg-blue-100 text-blue-700 rounded-2xl mx-auto flex items-center justify-center animate-bounce">
              <Plane className="w-6 h-6" />
            </div>
            <h4 className="font-bold text-slate-800 text-sm">खेत का एरियल स्कैन जारी है</h4>
            <p className="text-xs text-slate-500">EarthMind AI डेटा प्रोसेस कर रहा है...</p>
          </div>

          <ProgressStepper steps={progressSteps} currentPercent={scanPercent} />
        </div>
      ) : (
        /* Completed Result View */
        <div className="space-y-4 animate-in fade-in duration-300">
          <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-2">
              <div>
                <span className="text-xs font-bold text-slate-800">{scanResult?.fieldName}</span>
                <p className="text-[10px] text-slate-400">क्षेत्रफल: {scanResult?.areaScannedAcres} एकड़</p>
              </div>
              <span className="text-xs bg-emerald-100 text-emerald-800 font-bold px-2.5 py-0.5 rounded-full flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> ड्रोन स्कैन पूर्ण
              </span>
            </div>

            {/* Metrics */}
            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-medium">NDVI सूचकांक</span>
                <span className="text-sm font-extrabold text-emerald-700">{scanResult?.ndviScore} (अच्छा)</span>
              </div>
              <div className="p-3 bg-slate-50 rounded-xl border border-slate-100">
                <span className="text-[10px] text-slate-400 block font-medium">समग्र स्वास्थ्य</span>
                <span className="text-sm font-extrabold text-blue-700">{scanResult?.overallHealthScore}/100</span>
              </div>
            </div>

            {/* Recommendations */}
            <div className="p-3 bg-amber-50 rounded-xl border border-amber-200/80 text-xs text-amber-950 space-y-1">
              <span className="font-bold text-amber-900 block flex items-center gap-1">
                <AlertCircle className="w-4 h-4 text-amber-600" />
                मुख्य निष्कर्ष एवं सलाह:
              </span>
              <p className="text-[11px] leading-relaxed">{scanResult?.recommendationSummary}</p>
            </div>
          </div>

          <div className="flex gap-2">
            <button
              onClick={onOpenAssistant}
              className="flex-1 bg-emerald-800 hover:bg-emerald-900 text-white py-3 px-3 rounded-2xl font-bold text-xs flex items-center justify-center gap-1.5 shadow-md"
            >
              <Bot className="w-4 h-4" />
              <span>AI से पूछें</span>
            </button>
            <button
              onClick={onOpenFields}
              className="flex-1 bg-slate-800 hover:bg-slate-900 text-white py-3 px-3 rounded-2xl font-bold text-xs flex items-center justify-center gap-1.5 shadow-md"
            >
              <span>मेरे खेत देखें</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
