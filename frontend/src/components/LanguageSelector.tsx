import { Check, X, Globe } from 'lucide-react';
import type { LanguageCode } from '../types';
import { useTranslation, SUPPORTED_LANGUAGES } from '../i18n/useTranslation';

interface LanguageSelectorProps {
  isOpen: boolean;
  onClose: () => void;
}

export function LanguageSelector({ isOpen, onClose }: LanguageSelectorProps) {
  const { currentLanguage, changeLanguage } = useTranslation();

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4 animate-in fade-in duration-200">
      <div className="bg-white w-full max-w-md rounded-t-3xl sm:rounded-3xl shadow-2xl overflow-hidden max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="bg-emerald-800 text-white p-4 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Globe className="w-5 h-5 text-emerald-300" />
            <h3 className="font-bold text-base">भाषा चुनें / Choose Language</h3>
          </div>
          <button
            onClick={onClose}
            className="p-1 rounded-full hover:bg-emerald-700 transition text-emerald-200 hover:text-white"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Language Options Grid */}
        <div className="p-4 overflow-y-auto grid grid-cols-2 gap-3">
          {SUPPORTED_LANGUAGES.map((lang) => {
            const isSelected = currentLanguage === lang.code;
            return (
              <button
                key={lang.code}
                onClick={() => {
                  changeLanguage(lang.code as LanguageCode);
                  onClose();
                }}
                className={`p-3.5 rounded-2xl border text-left flex items-center justify-between transition-all ${
                  isSelected
                    ? 'border-emerald-600 bg-emerald-50 text-emerald-900 font-bold ring-2 ring-emerald-600/30 shadow-sm'
                    : 'border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-800 font-medium'
                }`}
              >
                <div>
                  <div className="text-sm font-semibold">{lang.name}</div>
                  <div className="text-[11px] text-slate-500">{lang.nativeName}</div>
                </div>
                {isSelected && (
                  <div className="w-5 h-5 rounded-full bg-emerald-600 text-white flex items-center justify-center">
                    <Check className="w-3.5 h-3.5" />
                  </div>
                )}
              </button>
            );
          })}
        </div>

        {/* Footer */}
        <div className="p-3 bg-slate-50 border-t border-slate-100 text-center text-xs text-slate-500">
          EarthMind किसान की अपनी भाषा का सम्मान करता है।
        </div>
      </div>
    </div>
  );
}
