import React, { useState, useEffect } from 'react';
import { ConsortiumRun } from '@/types';
import { fetchRuns, fetchRun } from '@/services/api';
import { GitCompare, RefreshCw, Hash, Award } from 'lucide-react';

export function CompareView() {
  const [runs, setRuns] = useState<ConsortiumRun[]>([]);
  const [left, setLeft] = useState<ConsortiumRun | null>(null);
  const [right, setRight] = useState<ConsortiumRun | null>(null);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setRuns(await fetchRuns(50)); } catch (e) { console.error(e); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  const openRun = async (id: string, side: 'left' | 'right') => {
    try {
      const run = await fetchRun(id);
      if (side === 'left') setLeft(run);
      else setRight(run);
    } catch (e) { console.error(e); }
  };

  const renderRunCard = (run: ConsortiumRun | null, side: 'left' | 'right') => (
    <div className="flex-1 bg-[#151D2E] border border-[#1E293B] rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-[#1E293B]">
        <h3 className="text-xs font-medium text-slate-300 uppercase tracking-wider">
          {side === 'left' ? 'Run A' : 'Run B'}
        </h3>
      </div>
      {run ? (
        <div className="p-4 space-y-3">
          <p className="text-xs text-slate-300 font-mono">{run.userPrompt}</p>
          <div className="flex items-center gap-4 text-[10px]">
            <span className="text-slate-500">Strategy: <span className="text-slate-300">{run.strategy}</span></span>
            <span className="text-slate-500">Conf: <span className="text-blue-400 data-number">{(run.finalConfidence * 100).toFixed(0)}%</span></span>
            <span className="text-slate-500">Iters: <span className="text-slate-300 data-number">{run.iterationCount}</span></span>
          </div>
          <div className="space-y-1.5 max-h-[50vh] overflow-y-auto">
            {run.iterations.map(iter => (
              <div key={iter.iteration} className="bg-[#0D1321] rounded p-2.5 border border-[#1E293B]">
                <div className="flex items-center justify-between mb-1">
                  <span className="text-[10px] text-slate-500">Iter {iter.iteration}</span>
                  <span className="text-[10px] text-slate-400 data-number">{(iter.synthesis.confidence * 100).toFixed(0)}%</span>
                </div>
                <p className="text-[10px] text-slate-400 line-clamp-2">{iter.synthesis.synthesis}</p>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="p-8 text-center">
          <p className="text-xs text-slate-600">Select a run to compare</p>
        </div>
      )}
    </div>
  );

  return (
    <div className="h-full flex flex-col bg-[#0A0F1A]">
      <div className="px-6 py-4 border-b border-[#1E293B] bg-[#0D1321]">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Compare Runs</h2>
            <p className="text-[11px] text-slate-600 mt-0.5">Side-by-side comparison of consortium executions</p>
          </div>
          <button onClick={load} className="p-2 rounded-md hover:bg-[#1A2332] text-slate-500 hover:text-slate-300">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="p-4 border-b border-[#1E293B]">
        <div className="grid grid-cols-2 gap-4">
          <select
            onChange={(e) => e.target.value && openRun(e.target.value, 'left')}
            className="w-full bg-[#0D1321] border border-[#1E293B] rounded-md px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500/50"
            value=""
          >
            <option value="">Select Run A...</option>
            {runs.map(r => (
              <option key={r.id} value={r.id}>{r.userPrompt?.slice(0, 60)} ({r.id.slice(0, 8)})</option>
            ))}
          </select>
          <select
            onChange={(e) => e.target.value && openRun(e.target.value, 'right')}
            className="w-full bg-[#0D1321] border border-[#1E293B] rounded-md px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500/50"
            value=""
          >
            <option value="">Select Run B...</option>
            {runs.map(r => (
              <option key={r.id} value={r.id}>{r.userPrompt?.slice(0, 60)} ({r.id.slice(0, 8)})</option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex-1 p-4 flex gap-4 overflow-hidden">
        {renderRunCard(left, 'left')}
        <div className="flex items-center justify-center w-8 flex-shrink-0">
          <GitCompare className="w-5 h-5 text-slate-600" />
        </div>
        {renderRunCard(right, 'right')}
      </div>
    </div>
  );
}
