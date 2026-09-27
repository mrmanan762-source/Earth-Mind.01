export type ActiveTab = 'home' | 'assistant' | 'crop-analysis' | 'soil-analysis' | 'drone-scan' | 'fields' | 'profile';

export type LanguageCode = 'hi' | 'en' | 'mai' | 'bho' | 'mr' | 'gu' | 'ta' | 'te';

export interface AssistantMessageItem {
  id: string;
  sender: 'user' | 'assistant';
  text: string;
  timestamp: string;
  confidence?: number;
  sources?: string[];
  suggestedFollowUps?: string[];
}

export interface CropAnalysisResult {
  id: string;
  cropName: string;
  condition: 'स्वास्थ (Healthy)' | 'सावधान (Warning)' | 'गंभीर (Critical)';
  confidence: number;
  suspectedIssue: string;
  recommendedActions: string[];
  followUpActions: string[];
  imageUrl: string;
  timestamp: string;
}

export interface SoilAnalysisResult {
  id: string;
  fieldName: string;
  phLevel: number;
  moisturePercentage: number;
  nitrogenLevel: string;
  phosphorusLevel: string;
  potassiumLevel: string;
  soilHealthIndex: number;
  recommendedFertilizer: string[];
  timestamp: string;
}

export interface DroneScanProgress {
  step?: number;
  title: string;
  percent: number;
  isComplete: boolean;
}

export interface DroneScanResult {
  id: string;
  fieldName: string;
  areaScannedAcres?: number;
  overallHealthScore: number;
  ndviScore: number;
  detectedStressAreas: number;
  recommendationSummary: string;
  timestamp: string;
  imagesCount: number;
}

export interface FieldInfo {
  id: string;
  name: string;
  areaAcres: number;
  cropName: string;
  soilType: string;
  lastInspectionDate: string;
  status: 'अच्छा (Good)' | 'ध्यान दें (Attention Needed)' | 'उत्कृष्ट (Excellent)';
  location: string;
}

export interface FarmerProfile {
  name: string;
  village: string;
  district: string;
  state: string;
  phoneNumber: string;
  language: LanguageCode;
  totalLandAcres: number;
  registeredFieldsCount: number;
}

export interface FieldHistoryItem {
  id: string;
  type: 'crop' | 'soil' | 'drone';
  title: string;
  fieldName: string;
  date: string;
  summary: string;
  statusBadge: string;
}
