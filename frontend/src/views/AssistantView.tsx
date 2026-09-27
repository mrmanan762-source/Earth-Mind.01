import { useState, useEffect, useRef } from 'react';
import { Send, Plus, Sparkles, Loader2, Info } from 'lucide-react';
import type { AssistantMessageItem } from '../types';
import { assistantService } from '../services/assistantService';
import { AssistantMessage } from '../components/AssistantMessage';
import { SuggestedQuestion } from '../components/SuggestedQuestion';
import { VoiceButton } from '../components/VoiceButton';
import { PlusToolMenu } from '../components/PlusToolMenu';

interface AssistantViewProps {
  onOpenCropAnalysis: () => void;
  onOpenSoilAnalysis: () => void;
  onOpenDroneScan: () => void;
  onOpenFields: () => void;
}

export function AssistantView({
  onOpenCropAnalysis,
  onOpenSoilAnalysis,
  onOpenDroneScan,
  onOpenFields,
}: AssistantViewProps) {
  const [messages, setMessages] = useState<AssistantMessageItem[]>([]);
  const [inputText, setInputText] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isPlusMenuOpen, setIsPlusMenuOpen] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    assistantService.getInitialMessages().then((msgs) => setMessages(msgs));
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const handleSend = async (textToSend?: string) => {
    const text = textToSend || inputText;
    if (!text.trim() || isLoading) return;

    setInputText('');
    setIsLoading(true);

    try {
      await assistantService.sendMessage({ text });
      const updated = await assistantService.getInitialMessages();
      setMessages(updated);
    } finally {
      setIsLoading(false);
    }
  };

  const suggestions = [
    'धान में पत्ती झुलसा का क्या इलाज है?',
    'यूरिया खाद कितनी मात्रा में डालनी चाहिए?',
    'मौसम का क्या पूर्वानुमान है?',
  ];

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] bg-slate-50 relative">
      {/* Top Helper Subheader */}
      <div className="bg-emerald-900 text-emerald-100 px-4 py-2 text-xs flex items-center justify-between border-b border-emerald-800">
        <div className="flex items-center gap-1.5 font-medium">
          <Sparkles className="w-3.5 h-3.5 text-amber-300" />
          <span>EarthMind AI कृषि सहायक</span>
        </div>
        <span className="text-[10px] bg-emerald-800/80 px-2 py-0.5 rounded-full border border-emerald-700">
          24x7 कृषि विशेषज्ञ मार्गदर्शन
        </span>
      </div>

      {/* Messages Thread */}
      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {messages.map((msg) => (
          <AssistantMessage
            key={msg.id}
            message={msg}
            onSelectFollowUp={(q) => handleSend(q)}
          />
        ))}

        {isLoading && (
          <div className="flex items-center gap-2 text-xs text-emerald-800 font-semibold bg-emerald-50 border border-emerald-200 p-3 rounded-2xl w-fit">
            <Loader2 className="w-4 h-4 animate-spin text-emerald-600" />
            <span>EarthMind कृषि ज्ञानकोष से सोच रहा है...</span>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Chips */}
      {messages.length < 3 && (
        <div className="px-4 pb-2">
          <p className="text-[11px] text-slate-500 font-medium mb-1.5 flex items-center gap-1">
            <Info className="w-3 h-3 text-slate-400" />
            सुझाए गए प्रश्न (Suggested Questions):
          </p>
          <div className="flex flex-col gap-1.5">
            {suggestions.map((q, idx) => (
              <SuggestedQuestion key={idx} text={q} onClick={() => handleSend(q)} />
            ))}
          </div>
        </div>
      )}

      {/* Assistant Composer Bar */}
      <div className="p-3 bg-white border-t border-slate-200 shadow-lg sticky bottom-0">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex items-center gap-2"
        >
          {/* CRITICAL PLUS BUTTON (+ TOOL MENU TRIGGER) */}
          <button
            type="button"
            onClick={() => setIsPlusMenuOpen(true)}
            aria-label="टूल्स खोलें"
            className="w-10 h-10 rounded-2xl bg-emerald-100 hover:bg-emerald-200 text-emerald-800 flex items-center justify-center flex-shrink-0 transition shadow-xs active:scale-95 border border-emerald-300/60"
          >
            <Plus className="w-6 h-6 stroke-[2.5]" />
          </button>

          {/* Text Input */}
          <div className="flex-1 relative">
            <input
              type="text"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              placeholder="EarthMind से अपनी समस्या पूछें..."
              className="w-full bg-slate-100 border border-slate-200 rounded-2xl py-2.5 pl-3.5 pr-10 text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-emerald-600 focus:bg-white text-slate-800 placeholder-slate-400"
            />
            <div className="absolute right-1.5 top-1/2 -translate-y-1/2">
              <VoiceButton onTranscript={(txt) => setInputText(txt)} />
            </div>
          </div>

          {/* Send Button */}
          <button
            type="submit"
            disabled={!inputText.trim() || isLoading}
            className={`w-10 h-10 rounded-2xl flex items-center justify-center flex-shrink-0 transition shadow-md ${
              inputText.trim() && !isLoading
                ? 'bg-emerald-700 hover:bg-emerald-800 text-white active:scale-95'
                : 'bg-slate-200 text-slate-400 cursor-not-allowed'
            }`}
          >
            <Send className="w-4 h-4" />
          </button>
        </form>
      </div>

      {/* Composer "+" Tool Menu Overlay */}
      <PlusToolMenu
        isOpen={isPlusMenuOpen}
        onClose={() => setIsPlusMenuOpen(false)}
        onSelectCropAnalysis={onOpenCropAnalysis}
        onSelectSoilAnalysis={onOpenSoilAnalysis}
        onSelectDroneScan={onOpenDroneScan}
        onSelectMyFields={onOpenFields}
      />
    </div>
  );
}
