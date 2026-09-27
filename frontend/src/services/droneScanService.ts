import type { DroneScanProgress, DroneScanResult } from '../types';
import { MOCK_DRONE_SCAN_DEFAULT } from '../mock/data';

export interface DroneScanRequest {
  imageFiles?: (File | string)[];
  fieldId: string;
}

export interface IDroneScanService {
  startScan(request: DroneScanRequest, onProgress?: (progress: DroneScanProgress) => void): Promise<DroneScanResult>;
  getScanHistory(): Promise<DroneScanResult[]>;
}

export class MockDroneScanService implements IDroneScanService {
  private history: DroneScanResult[] = [MOCK_DRONE_SCAN_DEFAULT];

  async startScan(request: DroneScanRequest, onProgress?: (progress: DroneScanProgress) => void): Promise<DroneScanResult> {
    const steps: DroneScanProgress[] = [
      { step: 1, title: 'तस्वीरें अपलोड हो रही हैं (Uploading Imagery)', percent: 20, isComplete: false },
      { step: 2, title: 'फसल स्वास्थ्य का नक्शा (Crop Health Mapping)', percent: 45, isComplete: false },
      { step: 3, title: 'मिट्टी की नमी और तनाव सूचकांक (Soil & Stress Index)', percent: 70, isComplete: false },
      { step: 4, title: 'मौसम डाटा समन्वय (Weather Data Alignment)', percent: 85, isComplete: false },
      { step: 5, title: 'EarthMind AI विश्लेषण (AI Deep Analysis)', percent: 100, isComplete: true },
    ];

    for (const p of steps) {
      if (onProgress) onProgress(p);
      await new Promise((r) => setTimeout(r, 600));
    }

    const result: DroneScanResult = {
      id: `drone-scan-${Date.now()}`,
      fieldName: request.fieldId === 'field-2' ? 'खेत 2 (नदी पास)' : 'खेत 1 (उत्तर दिशा)',
      areaScannedAcres: 2.5,
      overallHealthScore: 88,
      ndviScore: 0.76,
      detectedStressAreas: 2,
      recommendationSummary:
        'ड्रोन स्कैन में उत्तर-पूर्वी कोने में नमी की हल्की कमी और नाइट्रोजन का हल्का तनाव दिखा है। पानी की सिंचाई और सूक्ष्म पोषक तत्व छिड़काव की सलाह दी जाती है।',
      timestamp: new Date().toLocaleString('hi-IN', {
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }),
      imagesCount: request.imageFiles?.length || 4,
    };

    this.history.unshift(result);
    return result;
  }

  async getScanHistory(): Promise<DroneScanResult[]> {
    return [...this.history];
  }
}

export const droneScanService: IDroneScanService = new MockDroneScanService();
