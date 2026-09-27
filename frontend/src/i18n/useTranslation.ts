import { useState, useEffect } from 'react';
import type { LanguageCode } from '../types';
import { TRANSLATIONS } from './translations';

export interface LanguageOption {
  code: LanguageCode;
  name: string;
  nativeName: string;
}

export const SUPPORTED_LANGUAGES: LanguageOption[] = [
  { code: 'hi', name: 'Hindi', nativeName: 'हिंदी' },
  { code: 'en', name: 'English', nativeName: 'English' },
  { code: 'mai', name: 'Maithili', nativeName: 'मैथिली' },
  { code: 'bho', name: 'Bhojpuri', nativeName: 'भोजपुरी' },
  { code: 'mr', name: 'Marathi', nativeName: 'मराठी' },
  { code: 'gu', name: 'Gujarati', nativeName: 'गुजराती' },
  { code: 'ta', name: 'Tamil', nativeName: 'தமிழ்' },
  { code: 'te', name: 'Telugu', nativeName: 'తెలుగు' },
];

export function useTranslation() {
  const [lang, setLang] = useState<LanguageCode>(() => {
    return (localStorage.getItem('earthmind_lang') as LanguageCode) || 'hi';
  });

  useEffect(() => {
    localStorage.setItem('earthmind_lang', lang);
  }, [lang]);

  const t = (key: string): string => {
    const langDict = TRANSLATIONS[lang] || TRANSLATIONS['hi'];
    return langDict[key] || TRANSLATIONS['hi'][key] || key;
  };

  const currentLanguageOption =
    SUPPORTED_LANGUAGES.find((l) => l.code === lang) || SUPPORTED_LANGUAGES[0];

  return {
    lang,
    setLang,
    currentLanguage: lang,
    currentLanguageName: currentLanguageOption.nativeName,
    changeLanguage: (newLang: LanguageCode) => setLang(newLang),
    t,
    supportedLanguages: SUPPORTED_LANGUAGES,
  };
}
