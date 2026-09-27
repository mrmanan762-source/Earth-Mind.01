import { useState } from 'react';
import { Mic, MicOff } from 'lucide-react';

interface VoiceButtonProps {
  onTranscript: (text: string) => void;
}

export function VoiceButton({ onTranscript }: VoiceButtonProps) {
  const [isListening, setIsListening] = useState(false);

  const toggleListening = () => {
    if (isListening) {
      setIsListening(false);
    } else {
      setIsListening(true);
      // Simulate voice recognition in prototype
      setTimeout(() => {
        onTranscript('धान की फसल में पत्ती ब्लास्ट के लिए क्या छिड़काव करें?');
        setIsListening(false);
      }, 2500);
    }
  };

  return (
    <button
      type="button"
      onClick={toggleListening}
      aria-label={isListening ? 'बोलना बंद करें' : 'माइक्रोफोन से बोलें'}
      className={`p-2.5 rounded-full transition-all flex items-center justify-center ${
        isListening
          ? 'bg-red-500 text-white animate-pulse ring-4 ring-red-200'
          : 'bg-emerald-100 text-emerald-800 hover:bg-emerald-200'
      }`}
    >
      {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
    </button>
  );
}
