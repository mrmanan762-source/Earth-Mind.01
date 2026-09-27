import type { AssistantMessageItem } from '../types';
import { MOCK_ASSISTANT_INITIAL_MESSAGES } from '../mock/data';

export interface SendMessageRequest {
  text: string;
  attachedImage?: string;
  toolContext?: string;
}

export interface IAssistantService {
  getInitialMessages(): Promise<AssistantMessageItem[]>;
  sendMessage(request: SendMessageRequest): Promise<AssistantMessageItem>;
}

export class MockAssistantService implements IAssistantService {
  private messages: AssistantMessageItem[] = [...MOCK_ASSISTANT_INITIAL_MESSAGES];

  async getInitialMessages(): Promise<AssistantMessageItem[]> {
    return [...this.messages];
  }

  async sendMessage(request: SendMessageRequest): Promise<AssistantMessageItem> {
    await new Promise((resolve) => setTimeout(resolve, 800));

    const userMsg: AssistantMessageItem = {
      id: `user-${Date.now()}`,
      sender: 'user',
      text: request.text,
      timestamp: new Date().toLocaleTimeString('hi-IN', { hour: '2-digit', minute: '2-digit' }),
    };
    this.messages.push(userMsg);

    let replyText = 'धन्यवाद! EarthMind आपकी इस समस्या का विश्लेषण कर रहा है।';
    let followUps = ['मौसम का प्रभाव क्या होगा?', 'कितना पानी देना चाहिए?', 'खाद की मात्रा कितनी रखें?'];

    const lower = request.text.toLowerCase();
    if (lower.includes('धान') || lower.includes('पत्ती') || lower.includes('कीड़ा')) {
      replyText =
        'धान की फसल में पत्ती झुलसा (Leaf Blast) के लक्षण दिख रहे हैं। आपको ट्राइसाइक्लाजोल 75% WP (0.6 ग्राम/लीटर) का छिड़काव करने की सलाह दी जाती है। नाइट्रोजन यूरिया का अत्यधिक प्रयोग न करें।';
      followUps = ['दवा छिड़काव का सही समय क्या है?', 'पानी निकासी कैसे करें?'];
    } else if (lower.includes('यूरिया') || lower.includes('खाद')) {
      replyText =
        'धान/मक्का में नीम लेपित यूरिया का प्रयोग दो से तीन किश्तों में करें। प्रति एकड़ 40-45 किग्रा यूरिया पर्याप्त रहता है।';
    } else if (lower.includes('मौसम')) {
      replyText =
        'आपके समस्तीपुर क्षेत्र में अगले 3 दिनों तक मौसम साफ रहेगा, तापमान 32°C से 36°C के बीच रहेगा। सिंचाई के लिए उपयुक्त समय है।';
    }

    const assistantMsg: AssistantMessageItem = {
      id: `assistant-${Date.now()}`,
      sender: 'assistant',
      text: replyText,
      confidence: 94,
      sources: ['EarthMind C.2 Knowledge Base', 'ICAR Plant Protection Guidelines'],
      suggestedFollowUps: followUps,
      timestamp: new Date().toLocaleTimeString('hi-IN', { hour: '2-digit', minute: '2-digit' }),
    };

    this.messages.push(assistantMsg);
    return assistantMsg;
  }
}

export const assistantService: IAssistantService = new MockAssistantService();
