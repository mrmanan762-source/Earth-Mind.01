import { useState } from 'react';
import type { ActiveTab } from './types';
import { AppHeader } from './components/AppHeader';
import { BottomNavigation } from './components/BottomNavigation';
import { LanguageSelector } from './components/LanguageSelector';

import { HomeView } from './views/HomeView';
import { AssistantView } from './views/AssistantView';
import { CropAnalysisView } from './views/CropAnalysisView';
import { SoilAnalysisView } from './views/SoilAnalysisView';
import { DroneScanView } from './views/DroneScanView';
import { FieldsView } from './views/FieldsView';
import { ProfileView } from './views/ProfileView';

export function App() {
  const [activeTab, setActiveTab] = useState<ActiveTab>('home');
  const [isLanguageModalOpen, setIsLanguageModalOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-100 flex justify-center text-slate-800 antialiased selection:bg-emerald-200 selection:text-emerald-900">
      <div className="w-full max-w-md bg-white min-h-screen flex flex-col shadow-2xl relative pb-20 overflow-x-hidden">
        {/* Top Header */}
        <AppHeader
          onOpenLanguageModal={() => setIsLanguageModalOpen(true)}
          onNavigateHome={() => setActiveTab('home')}
        />

        {/* View Routing */}
        <main className="flex-1 overflow-y-auto">
          {activeTab === 'home' && (
            <HomeView
              onOpenAssistant={() => setActiveTab('assistant')}
              onOpenCropAnalysis={() => setActiveTab('crop-analysis')}
              onOpenSoilAnalysis={() => setActiveTab('soil-analysis')}
              onOpenDroneScan={() => setActiveTab('drone-scan')}
              onOpenFields={() => setActiveTab('fields')}
            />
          )}

          {activeTab === 'assistant' && (
            <AssistantView
              onOpenCropAnalysis={() => setActiveTab('crop-analysis')}
              onOpenSoilAnalysis={() => setActiveTab('soil-analysis')}
              onOpenDroneScan={() => setActiveTab('drone-scan')}
              onOpenFields={() => setActiveTab('fields')}
            />
          )}

          {activeTab === 'crop-analysis' && (
            <CropAnalysisView
              onOpenAssistant={() => setActiveTab('assistant')}
            />
          )}

          {activeTab === 'soil-analysis' && (
            <SoilAnalysisView
              onOpenAssistant={() => setActiveTab('assistant')}
            />
          )}

          {activeTab === 'drone-scan' && (
            <DroneScanView
              onOpenAssistant={() => setActiveTab('assistant')}
              onOpenFields={() => setActiveTab('fields')}
            />
          )}

          {activeTab === 'fields' && (
            <FieldsView
              onOpenCropAnalysis={() => setActiveTab('crop-analysis')}
              onOpenSoilAnalysis={() => setActiveTab('soil-analysis')}
              onOpenDroneScan={() => setActiveTab('drone-scan')}
            />
          )}

          {activeTab === 'profile' && (
            <ProfileView
              onOpenFields={() => setActiveTab('fields')}
              onOpenLanguageModal={() => setIsLanguageModalOpen(true)}
            />
          )}
        </main>

        {/* Bottom Bar */}
        <BottomNavigation
          activeTab={activeTab}
          onSelectTab={(tab: ActiveTab) => setActiveTab(tab)}
        />

        {/* Language Modal */}
        <LanguageSelector
          isOpen={isLanguageModalOpen}
          onClose={() => setIsLanguageModalOpen(false)}
        />
      </div>
    </div>
  );
}

export default App;
