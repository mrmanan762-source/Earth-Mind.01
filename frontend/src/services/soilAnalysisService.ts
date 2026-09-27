import type { SoilAnalysisResult } from '../types';
import { MOCK_SOIL_ANALYSIS_DEFAULT } from '../mock/data';

export interface SoilAnalysisRequest {
  imageFile?: File | string;
  fieldId?: string;
  phInput?: number;
  moistureInput?: number;
  soilType?: string;
}

export interface ISoilAnalysisService {
  analyzeSoil(request: SoilAnalysisRequest): Promise<SoilAnalysisResult>;
  getSoilHistory(): Promise<SoilAnalysisResult[]>;
}

export class MockSoilAnalysisService implements ISoilAnalysisService {
  private history: SoilAnalysisResult[] = [MOCK_SOIL_ANALYSIS_DEFAULT];

  async analyzeSoil(request: SoilAnalysisRequest): Promise<SoilAnalysisResult> {
    await new Promise((resolve) => setTimeout(resolve, 1000));

    const result: SoilAnalysisResult = {
      id: `soil-diag-${Date.now()}`,
      fieldName: request.fieldId === 'field-2' ? 'खेत 2 (नदी पास)' : 'खेत 1 (उत्तर दिशा)',
      phLevel: request.phInput || 6.8,
      moisturePercentage: request.moistureInput || 62,
      nitrogenLevel: 'मध्यम (Medium)',
      phosphorusLevel: 'पर्याप्त (Adequate)',
      potassiumLevel: 'उच्च (High)',
      soilHealthIndex: 88,
      recommendedFertilizer: [
        'नीम लेपित यूरिया: 40-45 किग्रा/एकड़',
        'जिंक सल्फेट 21%: 10 किग्रा/एकड़',
        'गोबर की पकी खाद या वर्मीकम्पोस्ट का नियमित प्रयोग करें',
      ],
      timestamp: new Date().toLocaleString('hi-IN', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }),
    };

    this.history.unshift(result);
    return result;
  }

  async getSoilHistory(): Promise<SoilAnalysisResult[]> {
    return [...this.history];
  }
}

export const soilAnalysisService: ISoilAnalysisService = new MockSoilAnalysisService();
