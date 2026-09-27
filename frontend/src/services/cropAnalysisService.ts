import type { CropAnalysisResult } from '../types';
import { MOCK_CROP_ANALYSIS_DEFAULT } from '../mock/data';

export interface CropAnalysisRequest {
  imageFile?: File | string;
  fieldId?: string;
  note?: string;
}

export interface ICropAnalysisService {
  analyzeCrop(request: CropAnalysisRequest): Promise<CropAnalysisResult>;
  getHistory(): Promise<CropAnalysisResult[]>;
}

export class MockCropAnalysisService implements ICropAnalysisService {
  private history: CropAnalysisResult[] = [MOCK_CROP_ANALYSIS_DEFAULT];

  async analyzeCrop(request: CropAnalysisRequest): Promise<CropAnalysisResult> {
    await new Promise((resolve) => setTimeout(resolve, 1200));

    const result: CropAnalysisResult = {
      id: `crop-diag-${Date.now()}`,
      cropName: request.fieldId === 'field-2' ? 'मक्का (Maize)' : 'धान (Paddy)',
      condition: 'सावधान (Warning)',
      confidence: 94,
      suspectedIssue: 'पत्ती झुलसा एवं कीट संक्रमण (Leaf Spot & Pest Vulnerability)',
      recommendedActions: [
        'पत्तियों पर नीम तेल (5 मिली/लीटर) या अनुशंसित कीटनाशक का छिड़काव करें।',
        'खेत में जलभराव की स्थिति न होने दें, जल निकासी बनाए रखें।',
        '3 दिन बाद पुनः फसल फोटो लेकर स्थिति का आकलन करें।',
      ],
      followUpActions: [
        'पड़ोसी खेतों में प्रसार से बचने के लिए तुरंत उपचार शुरू करें।',
        'EarthMind AI से फसल पोषण सलाह लें।',
      ],
      imageUrl:
        typeof request.imageFile === 'string'
          ? request.imageFile
          : 'https://images.unsplash.com/photo-1530595467537-0b5996c41f2d?auto=format&fit=crop&w=600&q=80',
      timestamp: new Date().toLocaleString('hi-IN', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      }),
    };

    this.history.unshift(result);
    return result;
  }

  async getHistory(): Promise<CropAnalysisResult[]> {
    return [...this.history];
  }
}

export const cropAnalysisService: ICropAnalysisService = new MockCropAnalysisService();
