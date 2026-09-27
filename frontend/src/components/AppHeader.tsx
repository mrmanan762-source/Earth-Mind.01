import { Globe, Sprout } from 'lucide-react';
import { useTranslation } from '../i18n/useTranslation';
import logoImg from '../assets/logo.png';

interface AppHeaderProps {
  onOpenLanguageModal: () => void;
  onNavigateHome: () => void;
}

export function AppHeader({ onOpenLanguageModal, onNavigateHome }: AppHeaderProps) {
  const { currentLanguageName } = useTranslation();

  return (
    <header className="sticky top-0 z-30 bg-emerald-800 text-white shadow-md border-b border-emerald-700/50 px-4 py-3 flex items-center justify-between">
      {/* Brand & Logo */}
      <button
        onClick={onNavigateHome}
        className="flex items-center gap-2.5 text-left focus:outline-none group"
      >
        <div className="bg-white/10 p-1 rounded-xl backdrop-blur-sm border border-white/20 group-hover:bg-white/20 transition">
          <img src={logoImg} alt="EarthMind Logo" className="w-8 h-8 object-contain" />
        </div>
        <div>
          <div className="flex items-center gap-1">
            <span className="font-bold text-lg tracking-tight text-emerald-50">EarthMind</span>
            <Sprout className="w-4 h-4 text-emerald-300" />
          </div>
          <p className="text-[10px] text-emerald-200 font-medium">कृषि का सच्चा साथी</p>
        </div>
      </button>

      {/* Language Trigger */}
      <button
        onClick={onOpenLanguageModal}
        className="flex items-center gap-1.5 bg-emerald-950/40 hover:bg-emerald-950/60 text-emerald-100 text-xs px-2.5 py-1.5 rounded-full border border-emerald-600/40 transition font-medium"
      >
        <Globe className="w-3.5 h-3.5 text-emerald-300" />
        <span>{currentLanguageName}</span>
      </button>
    </header>
  );
}
