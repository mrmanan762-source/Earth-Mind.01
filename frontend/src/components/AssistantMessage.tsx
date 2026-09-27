import { Bot, User } from 'lucide-react';
import type { AssistantMessageItem } from '../types';
import { ConfidenceIndicator } from './ConfidenceIndicator';

interface AssistantMessageProps {
  message: AssistantMessageItem;
  onSelectFollowUp?: (text: string) => void;
}

export function AssistantMessage({ message, onSelectFollowUp }: AssistantMessageProps) {
  const isUser = message.sender === 'user';

  return (
    <div className={`flex gap-2.5 ${isUser ? 'flex-row-reverse' : 'flex-row'} mb-4`}>
      {/* Avatar */}
      <div
        className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 shadow-sm ${
          isUser ? 'bg-slate-700 text-white' : 'bg-emerald-700 text-white'
        }`}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Content */}
      <div className={`max-w-[82%] space-y-2`}>
        <div
          className={`p-3.5 rounded-2xl text-xs sm:text-sm leading-relaxed shadow-sm ${
            isUser
              ? 'bg-emerald-800 text-white rounded-tr-none'
              : 'bg-white text-slate-800 border border-slate-200/80 rounded-tl-none'
          }`}
        >
          <p className="whitespace-pre-line font-normal">{message.text}</p>

          {!isUser && message.confidence && (
            <div className="mt-2.5 pt-2 border-t border-slate-100 flex items-center justify-between">
              <ConfidenceIndicator score={message.confidence} />
              <span className="text-[10px] text-slate-400">{message.timestamp}</span>
            </div>
          )}

          {isUser && (
            <div className="text-[10px] text-emerald-200 text-right mt-1 font-medium">
              {message.timestamp}
            </div>
          )}
        </div>

        {/* Suggested Follow ups */}
        {!isUser && message.suggestedFollowUps && message.suggestedFollowUps.length > 0 && (
          <div className="flex flex-wrap gap-1.5 pt-1">
            {message.suggestedFollowUps.map((q, idx) => (
              <button
                key={idx}
                onClick={() => onSelectFollowUp && onSelectFollowUp(q)}
                className="text-[11px] bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200/70 px-2.5 py-1 rounded-full text-left transition"
              >
                💡 {q}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
