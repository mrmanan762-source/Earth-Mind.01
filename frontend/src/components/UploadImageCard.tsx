import { useState } from 'react';
import { Camera, Image as ImageIcon, CheckCircle2 } from 'lucide-react';

interface UploadImageCardProps {
  title: string;
  description: string;
  onImageSelected: (imageSource: string) => void;
}

export function UploadImageCard({ title, description, onImageSelected }: UploadImageCardProps) {
  const [selectedPreview, setSelectedPreview] = useState<string | null>(null);

  const mockSamples = [
    {
      id: 'sample-1',
      title: 'धान फोटो 1',
      url: 'https://images.unsplash.com/photo-1530595467537-0b5996c41f2d?auto=format&fit=crop&w=400&q=80',
    },
    {
      id: 'sample-2',
      title: 'मक्का फोटो 2',
      url: 'https://images.unsplash.com/photo-1595855759920-86582396756a?auto=format&fit=crop&w=400&q=80',
    },
  ];

  const handleSelect = (url: string) => {
    setSelectedPreview(url);
    onImageSelected(url);
  };

  return (
    <div className="bg-white rounded-2xl p-4 border border-slate-200 shadow-sm space-y-3">
      <div>
        <h4 className="font-bold text-slate-800 text-sm">{title}</h4>
        <p className="text-xs text-slate-500 mt-0.5">{description}</p>
      </div>

      {/* Main Upload Actions */}
      <div className="grid grid-cols-2 gap-3 pt-1">
        <button
          onClick={() => handleSelect(mockSamples[0].url)}
          className="p-3.5 rounded-xl border-2 border-dashed border-emerald-300 bg-emerald-50/50 hover:bg-emerald-50 text-emerald-800 flex flex-col items-center justify-center gap-1.5 transition text-xs font-semibold"
        >
          <Camera className="w-5 h-5 text-emerald-600" />
          <span>कैमरा खोलें</span>
        </button>

        <button
          onClick={() => handleSelect(mockSamples[1].url)}
          className="p-3.5 rounded-xl border-2 border-dashed border-slate-300 bg-slate-50 hover:bg-slate-100 text-slate-700 flex flex-col items-center justify-center gap-1.5 transition text-xs font-semibold"
        >
          <ImageIcon className="w-5 h-5 text-slate-600" />
          <span>गैलरी से चुनें</span>
        </button>
      </div>

      {/* Prototype Quick Samples */}
      <div className="pt-2">
        <span className="text-[11px] text-slate-500 font-medium block mb-2">
          या नमूना फोटो का उपयोग करें (Demo Sample):
        </span>
        <div className="flex gap-2">
          {mockSamples.map((sample) => (
            <button
              key={sample.id}
              onClick={() => handleSelect(sample.url)}
              className={`relative flex-1 rounded-xl overflow-hidden border-2 transition ${
                selectedPreview === sample.url
                  ? 'border-emerald-600 ring-2 ring-emerald-600/30'
                  : 'border-slate-200 opacity-80 hover:opacity-100'
              }`}
            >
              <img src={sample.url} alt={sample.title} className="w-full h-16 object-cover" />
              <div className="absolute bottom-0 inset-x-0 bg-slate-900/70 text-white text-[10px] py-0.5 px-1 text-center font-medium">
                {sample.title}
              </div>
              {selectedPreview === sample.url && (
                <div className="absolute top-1 right-1 bg-emerald-600 text-white p-0.5 rounded-full">
                  <CheckCircle2 className="w-3.5 h-3.5" />
                </div>
              )}
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
