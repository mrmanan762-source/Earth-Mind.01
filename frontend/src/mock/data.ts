import type {
  AssistantMessageItem,
  CropAnalysisResult,
  SoilAnalysisResult,
  DroneScanResult,
  FieldInfo,
  FarmerProfile,
  FieldHistoryItem,
} from '../types';

export const MOCK_FARMER_PROFILE: FarmerProfile = {
  name: 'रामकुमार पटेल',
  village: 'शाहपुर गाँव',
  district: 'समस्तीपुर',
  state: 'बिहार',
  phoneNumber: '+91 98765 43210',
  language: 'hi',
  totalLandAcres: 5.5,
  registeredFieldsCount: 2,
};

export const MOCK_FIELDS: FieldInfo[] = [
  {
    id: 'field-1',
    name: 'खेत 1 (उत्तर दिशा)',
    areaAcres: 3.0,
    cropName: 'धान (Paddy - Sambha Mahsuri)',
    soilType: 'दोमट मिट्टी (Loam Soil)',
    lastInspectionDate: '12 मई 2024',
    status: 'उत्कृष्ट (Excellent)',
    location: 'उत्तर ब्लॉक, प्लाट सं. 14',
  },
  {
    id: 'field-2',
    name: 'खेत 2 (नदी पास)',
    areaAcres: 2.5,
    cropName: 'मक्का (Maize)',
    soilType: 'बलुई दोमट (Sandy Loam)',
    lastInspectionDate: '8 मई 2024',
    status: 'ध्यान दें (Attention Needed)',
    location: 'दक्षिणी छोर, प्लाट सं. 08',
  },
];

export const MOCK_CROP_ANALYSIS_DEFAULT: CropAnalysisResult = {
  id: 'crop-diag-101',
  cropName: 'धान (Paddy)',
  condition: 'सावधान (Warning)',
  confidence: 92,
  suspectedIssue: 'लीफ ब्लास्ट रोग (Leaf Blast Disease - Pyricularia oryzae)',
  recommendedActions: [
    'ट्राइसाइक्लाजोल 75% WP (0.6 ग्राम प्रति लीटर पानी) का तुरंत छिड़काव करें।',
    'खेत में नाइट्रोजन उर्वरक की अत्यधिक खुराक रोकने पर ध्यान दें।',
    'सिंचाई का जलस्तर उचित स्तर (2-3 सेमी) बनाकर रखें।',
  ],
  followUpActions: [
    '3 दिनों के बाद फिर से फसल की फोटो खींचकर जाँच करें।',
    'पड़ोसी खेतों में संक्रमण फैलने से रोकें।',
  ],
  imageUrl: 'https://images.unsplash.com/photo-1530595467537-0b5996c41f2d?auto=format&fit=crop&w=600&q=80',
  timestamp: '15 मई 2024, दोपहर 02:30',
};

export const MOCK_SOIL_ANALYSIS_DEFAULT: SoilAnalysisResult = {
  id: 'soil-diag-201',
  fieldName: 'खेत 1 (उत्तर दिशा)',
  phLevel: 6.8,
  moisturePercentage: 65,
  nitrogenLevel: 'मध्यम (Medium)',
  phosphorusLevel: 'पर्याप्त (Adequate)',
  potassiumLevel: 'उच्च (High)',
  soilHealthIndex: 88,
  recommendedFertilizer: [
    'नीम लेपित यूरिया: 45 किग्रा/एकड़',
    'जिंक सल्फेट: 10 किग्रा/एकड़',
    'जैविक खाद (वर्मीकम्पोस्ट): 2 क्विंटल/एकड़',
  ],
  timestamp: '10 मई 2024, सुबह 11:15',
};

export const MOCK_DRONE_SCAN_DEFAULT: DroneScanResult = {
  id: 'drone-scan-301',
  fieldName: 'खेत 1 (उत्तर दिशा)',
  areaScannedAcres: 3.0,
  overallHealthScore: 88,
  ndviScore: 0.78,
  detectedStressAreas: 2,
  recommendationSummary:
    'खेत के उत्तर-पूर्वी हिस्से में नमी और नाइट्रोजन तनाव पाया गया है। वहाँ लक्षित सिंचाई तथा सूक्ष्म पोषक तत्व की आवश्यकता है।',
  timestamp: '14 मई 2024, सुबह 09:00',
  imagesCount: 12,
};

export const MOCK_ASSISTANT_INITIAL_MESSAGES: AssistantMessageItem[] = [
  {
    id: 'msg-1',
    sender: 'assistant',
    text: 'नमस्ते रामकुमार जी! मैं आपका EarthMind कृषि साथी हूँ। आज मैं आपके खेत और फसल की क्या सहायता कर सकता हूँ?',
    timestamp: 'सुबह 10:00',
    suggestedFollowUps: [
      'धान में पत्ती झुलसा का क्या इलाज है?',
      'यूरिया खाद कितनी मात्रा में डालनी चाहिए?',
      'मौसम का क्या पूर्वानुमान है?',
    ],
  },
];

export const MOCK_FIELD_HISTORY: FieldHistoryItem[] = [
  {
    id: 'hist-1',
    type: 'crop',
    title: 'धान - पत्ती ब्लास्ट जाँच',
    fieldName: 'खेत 1 (उत्तर दिशा)',
    date: '15 मई 2024',
    summary: 'रोग पाया गया: लीफ ब्लास्ट (92% आत्मविश्वास)',
    statusBadge: 'सावधान',
  },
  {
    id: 'hist-2',
    type: 'drone',
    title: '3.0 एकड़ ड्रोन एरियल स्कैन',
    fieldName: 'खेत 1 (उत्तर दिशा)',
    date: '14 मई 2024',
    summary: 'NDVI इंडेक्स 0.78 - समग्र स्वास्थ्य अच्छा है',
    statusBadge: 'सफल',
  },
  {
    id: 'hist-3',
    type: 'soil',
    title: 'मिट्टी स्वास्थ्य रिपोर्ट',
    fieldName: 'खेत 1 (उत्तर दिशा)',
    date: '10 मई 2024',
    summary: 'pH 6.8, नमी 65% - नाइट्रोजन पूर्ति की आवश्यकता',
    statusBadge: 'उत्कृष्ट',
  },
];
