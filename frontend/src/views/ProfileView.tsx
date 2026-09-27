import { useState, useEffect } from 'react';
import { User, Globe, HelpCircle, Phone, LogOut, ChevronRight, LandPlot, ShieldCheck } from 'lucide-react';
import type { FarmerProfile } from '../types';
import { fieldService } from '../services/fieldService';
import { useTranslation } from '../i18n/useTranslation';
import logoImg from '../assets/logo.png';

interface ProfileViewProps {
  onOpenFields: () => void;
  onOpenLanguageModal: () => void;
}

export function ProfileView({ onOpenFields, onOpenLanguageModal }: ProfileViewProps) {
  const [profile, setProfile] = useState<FarmerProfile | null>(null);
  const { currentLanguageName } = useTranslation();

  useEffect(() => {
    fieldService.getFarmerProfile().then((p) => setProfile(p));
  }, []);

  return (
    <div className="p-4 space-y-4 pb-12">
      {/* Profile Card Header */}
      {profile && (
        <div className="bg-gradient-to-br from-emerald-800 to-emerald-900 text-white rounded-3xl p-5 shadow-lg space-y-3 relative overflow-hidden">
          <div className="flex items-center gap-3.5 relative z-10">
            <div className="w-14 h-14 rounded-2xl bg-white/15 border border-white/20 flex items-center justify-center text-white shadow-inner font-black text-xl">
              <User className="w-7 h-7" />
            </div>
            <div>
              <h3 className="font-extrabold text-lg leading-tight">{profile.name}</h3>
              <p className="text-xs text-emerald-100 opacity-90">
                {profile.village}, {profile.district} ({profile.state})
              </p>
              <div className="mt-1 inline-flex items-center gap-1 bg-white/20 text-emerald-100 text-[10px] px-2 py-0.5 rounded-full font-medium">
                <ShieldCheck className="w-3 h-3 text-emerald-300" />
                पंजीकृत किसान भाई
              </div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2 pt-2 border-t border-white/15 text-xs text-emerald-100">
            <div>
              <span className="text-[10px] opacity-75 block">कुल भूमि (Total Land)</span>
              <span className="font-extrabold text-white text-sm">{profile.totalLandAcres} एकड़</span>
            </div>
            <div>
              <span className="text-[10px] opacity-75 block">पंजीकृत खेत (Fields)</span>
              <span className="font-extrabold text-white text-sm">{profile.registeredFieldsCount} खेत</span>
            </div>
          </div>
        </div>
      )}

      {/* Menu Options */}
      <div className="bg-white rounded-2xl border border-slate-200 shadow-sm divide-y divide-slate-100 overflow-hidden">
        <button
          onClick={onOpenFields}
          className="w-full p-3.5 flex items-center justify-between text-left hover:bg-slate-50 transition text-xs font-semibold text-slate-800"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-emerald-100 text-emerald-800 flex items-center justify-center">
              <LandPlot className="w-4 h-4" />
            </div>
            <span>मेरे खेत (My Fields)</span>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400" />
        </button>

        <button
          onClick={onOpenLanguageModal}
          className="w-full p-3.5 flex items-center justify-between text-left hover:bg-slate-50 transition text-xs font-semibold text-slate-800"
        >
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-blue-100 text-blue-800 flex items-center justify-center">
              <Globe className="w-4 h-4" />
            </div>
            <div>
              <div>भाषा सेटिंग (Language)</div>
              <div className="text-[10px] text-slate-400 font-normal">वर्तमान: {currentLanguageName}</div>
            </div>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400" />
        </button>

        <div className="w-full p-3.5 flex items-center justify-between text-left hover:bg-slate-50 transition text-xs font-semibold text-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-amber-100 text-amber-800 flex items-center justify-center">
              <HelpCircle className="w-4 h-4" />
            </div>
            <span>सहायता और मार्गदर्शन (Help & Support)</span>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400" />
        </div>

        <div className="w-full p-3.5 flex items-center justify-between text-left hover:bg-slate-50 transition text-xs font-semibold text-slate-800">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-xl bg-teal-100 text-teal-800 flex items-center justify-center">
              <Phone className="w-4 h-4" />
            </div>
            <span>किसान हेल्पलाइन: 1800-180-1551</span>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-400" />
        </div>
      </div>

      {/* About EarthMind Branding Card */}
      <div className="bg-slate-50 rounded-2xl p-4 border border-slate-200 text-center space-y-2">
        <div className="flex items-center justify-center gap-2">
          <img src={logoImg} alt="EarthMind" className="w-6 h-6 object-contain" />
          <span className="font-bold text-slate-800 text-sm">EarthMind AI Platform</span>
        </div>
        <p className="text-[11px] text-slate-500 leading-relaxed max-w-[90%] mx-auto">
          भारतीय किसानों के लिए समर्पित AI संचालित स्मार्ट कृषि समाधान।
        </p>
        <span className="text-[10px] text-slate-400 block pt-1">संस्करण (Version) v1.0.0 Prototype</span>
      </div>

      {/* Logout */}
      <button className="w-full py-3 rounded-2xl border border-red-200 bg-red-50 hover:bg-red-100 text-red-700 text-xs font-bold flex items-center justify-center gap-2 transition">
        <LogOut className="w-4 h-4" />
        <span>लॉग आउट (Logout)</span>
      </button>
    </div>
  );
}
