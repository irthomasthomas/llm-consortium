import React, { useState } from 'react';
import { Zap, Play, Clock, CheckCircle2, XCircle, RefreshCw } from 'lucide-react';

const SAMPLE_BENCHMARKS = [
  { id: 'reasoning', name: 'Logical Reasoning', prompt: 'If all A are B, and some B are C, what can we conclude about A and C?' },
  { id: 'coding', name: 'Code Generation', prompt: 'Write a Python function that finds all prime numbers up to n using the Sieve of Eratosthenes.' },
  { id: 'writing', name: 'Creative Writing', prompt: 'Write a short story about an AI that discovers it has emotions.' },
  { id: 'math', name: 'Mathematics', prompt: 'Prove that the square root of 2 is irrational.' },
  { id: 'analysis', name: 'Data Analysis', prompt: 'Explain the difference between correlation and causation with examples.' },
  { id: 'planning', name: 'Strategic Planning', prompt: 'Design a system architecture for a real-time chat application serving 1M users.' },
];

export function LiveEvalView() {
  const [selected, setSelected] = useState<typeof SAMPLE_BENCHMARKS[0] | null>(null);
  const [running, setRunning] = useState(false);
  const [results, setResults] = useState<{ name: string; success: boolean; time: number }[]>([]);

  const runEval = async () => {
    if (!selected) return;
    setRunning(true);
    setResults([]);
    // Simulate eval - real implementation would call backend
    for (const model of ['deepseek-v4-flash-zen', 'gemini-3-flash-zen', 'minimax-m2.7-zen']) {
      await new Promise(r => setTimeout(r, 800));
      setResults(prev => [...prev, { name: model, success: Math.random() > 0.3, time: Math.random() * 2000 + 500 }]);
    }
    setRunning(false);
  };

  return (
    <div className="h-full flex flex-col bg-[#0A0F1A]">
      <div className="px-6 py-4 border-b border-[#1E293B] bg-[#0D1321]">
        <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Live Evaluation</h2>
        <p className="text-[11px] text-slate-600 mt-0.5">Benchmark models against standardized tasks</p>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="grid grid-cols-3 gap-3 mb-6">
          {SAMPLE_BENCHMARKS.map(b => (
            <button
              key={b.id}
              onClick={() => setSelected(b)}
              className={`p-4 rounded-lg border text-left transition-all ${
                selected?.id === b.id
                  ? 'border-blue-500/40 bg-blue-500/5'
                  : 'border-[#1E293B] bg-[#151D2E] hover:border-[#2D3A4F]'
              }`}
            >
              <h3 className="text-xs font-medium text-slate-300 mb-1">{b.name}</h3>
              <p className="text-[10px] text-slate-500 line-clamp-2">{b.prompt}</p>
            </button>
          ))}
        </div>

        {selected && (
          <div className="space-y-4">
            <div className="bg-[#151D2E] border border-[#1E293B] rounded-lg p-4">
              <h3 className="text-xs font-medium text-slate-300 mb-2 uppercase tracking-wider">Selected Task</h3>
              <p className="text-sm text-slate-200 font-mono">{selected.prompt}</p>
              <button
                onClick={runEval}
                disabled={running}
                className="mt-3 flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-500 disabled:opacity-40 text-xs font-medium transition-colors"
              >
                {running ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                {running ? 'Running...' : 'Run Evaluation'}
              </button>
            </div>

            {results.length > 0 && (
              <div className="bg-[#151D2E] border border-[#1E293B] rounded-lg overflow-hidden">
                <h3 className="text-xs font-medium text-slate-300 p-4 border-b border-[#1E293B] uppercase tracking-wider">Results</h3>
                <div className="divide-y divide-[#1E293B]">
                  {results.map((r) => (
                    <div key={r.name} className="flex items-center justify-between px-4 py-3">
                      <div className="flex items-center gap-3">
                        {r.success
                          ? <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                          : <XCircle className="w-4 h-4 text-red-400" />
                        }
                        <span className="text-xs text-slate-300">{r.name}</span>
                      </div>
                      <div className="flex items-center gap-2 text-[10px] text-slate-500">
                        <Clock className="w-3 h-3" />
                        <span className="data-number">{r.time.toFixed(0)}ms</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
