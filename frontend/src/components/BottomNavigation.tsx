import { Home, Bot, LandPlot, User } from 'lucide-react';
import type { ActiveTab } from '../types';
import { useTranslation } from '../i18n/useTranslation';

interface BottomNavigationProps {
  activeTab: ActiveTab;
  onSelectTab: (tab: ActiveTab) => void;
}

export function BottomNavigation({ activeTab, onSelectTab }: BottomNavigationProps) {
  const { t } = useTranslation();

  const navItems = [
    { id: 'home' as ActiveTab, label: t('nav.home'), icon: Home },
    { id: 'assistant' as ActiveTab, label: t('nav.assistant'), icon: Bot },
    { id: 'fields' as ActiveTab, label: t('nav.fields'), icon: LandPlot },
    { id: 'profile' as ActiveTab, label: t('nav.profile'), icon: User },
  ];

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-40 bg-white/95 backdrop-blur-md border-t border-slate-200 shadow-lg">
      <div className="max-w-md mx-auto flex items-center justify-around py-2 px-3">
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive =
            activeTab === item.id ||
            (item.id === 'assistant' &&
              (activeTab === 'crop-analysis' ||
                activeTab === 'soil-analysis' ||
                activeTab === 'drone-scan'));

          return (
            <button
              key={item.id}
              onClick={() => onSelectTab(item.id)}
              className={`flex flex-col items-center justify-center py-1 px-3 rounded-2xl transition-all duration-200 ${
                isActive
                  ? 'text-emerald-700 font-semibold scale-105'
                  : 'text-slate-500 hover:text-slate-700 font-medium'
              }`}
            >
              <div
                className={`p-1.5 rounded-full ${
                  isActive ? 'bg-emerald-100 text-emerald-800' : 'bg-transparent'
                }`}
              >
                <Icon className="w-5 h-5" />
              </div>
              <span className="text-[11px] mt-0.5 tracking-tight">{item.label}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
