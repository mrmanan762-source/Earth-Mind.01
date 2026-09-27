import type { FarmerProfile, FieldInfo } from '../types';
import { MOCK_FIELDS, MOCK_FARMER_PROFILE } from '../mock/data';

export interface IFieldService {
  getFarmerProfile(): Promise<FarmerProfile>;
  getFields(): Promise<FieldInfo[]>;
  getFieldById(id: string): Promise<FieldInfo | undefined>;
}

export class MockFieldService implements IFieldService {
  async getFarmerProfile(): Promise<FarmerProfile> {
    return { ...MOCK_FARMER_PROFILE };
  }

  async getFields(): Promise<FieldInfo[]> {
    return [...MOCK_FIELDS];
  }

  async getFieldById(id: string): Promise<FieldInfo | undefined> {
    return MOCK_FIELDS.find((f) => f.id === id);
  }
}

export const fieldService: IFieldService = new MockFieldService();
