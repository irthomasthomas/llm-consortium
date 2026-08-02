import React, { useState, useEffect } from 'react';
import { ConsortiumRun } from '@/types';
import { fetchRuns, fetchRun } from '@/services/api';
import {
  Clock, Hash, Award, Search, RefreshCw, ExternalLink, Database,
} from 'lucide-react';

export function HistoryView() {
  const [runs, setRuns] = useState<ConsortiumRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<ConsortiumRun | null>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);

  const loadRuns = async () => {
    setLoading(true);
    try {
      const data = await fetchRuns(100);
      setRuns(data);
    } catch (e) {
      console.error(e);
    }
    setLoading(false);
  };

  useEffect(() => { loadRuns(); }, []);

  const filtered = runs.filter(r =>
    !search || r.userPrompt.toLowerCase().includes(search.toLowerCase()) ||
    (r.configName && r.configName.toLowerCase().includes(search.toLowerCase()))
  );

  const openRun = async (runId: string) => {
    try {
      const run = await fetchRun(runId);
      setSelectedRun(run);
    } catch (e) {
      console.error(e);
    }
  };

  const confColor = (c: number) => c >= 0.8 ? 'text-emerald-400' : c >= 0.6 ? 'text-amber-400' : 'text-red-400';

  return (
    <div className="h-full flex flex-col bg-[#0A0F1A]">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[#1E293B] bg-[#0D1321]">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Run History</h2>
            <p className="text-[11px] text-slate-600 mt-0.5">Browse and inspect past consortium executions</p>
          </div>
          <button onClick={loadRuns} className="p-2 rounded-md hover:bg-[#1A2332] text-slate-500 hover:text-slate-300 transition-colors">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="px-6 py-3 border-b border-[#1E293B]">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-600" />
          <input
            type="text" value={search} onChange={e => setSearch(e.target.value)}
            placeholder="Search by prompt or config name..."
            className="w-full bg-[#0D1321] border border-[#1E293B] rounded-md pl-9 pr-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-blue-500/50"
          />
        </div>
      </div>

      {/* Run list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 && !loading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Database className="w-10 h-10 text-slate-700 mx-auto mb-3" />
              <p className="text-sm text-slate-500">No runs found</p>
              <p className="text-[11px] text-slate-600 mt-1">Run a consortium from the Studio to see results here</p>
            </div>
          </div>
        )}
        {filtered.map((run) => (
          <button
            key={run.id}
            onClick={() => openRun(run.id)}
            className={`w-full text-left px-6 py-3 border-b border-[#1E293B]/50 hover:bg-[#0D1321]/50 transition-colors ${
              selectedRun?.id === run.id ? 'bg-blue-500/5 border-l-2 border-l-blue-500' : ''
            }`}
          >
            <div className="flex items-center justify-between mb-1">
              <div className="flex items-center gap-3">
                <span className="text-xs font-medium text-slate-300 truncate max-w-md">
                  {run.userPrompt || '(no prompt)'}
                </span>
              </div>
              <div className="flex items-center gap-3 flex-shrink-0">
                <span className={`text-[11px] font-bold data-number ${confColor(run.finalConfidence)}`}>
                  {(run.finalConfidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div className="flex items-center gap-4 text-[10px] text-slate-600">
              <span className="flex items-center gap-1"><Hash className="w-3 h-3" />{run.iterationCount}/{run.maxIterations}</span>
              <span>{run.strategy}</span>
              {run.configName && <span className="text-slate-500">{run.configName}</span>}
              <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{new Date(run.createdAt).toLocaleDateString()}</span>
              <span className="text-slate-700 font-mono">{run.id.slice(0, 8)}</span>
            </div>
          </button>
        ))}
      </div>

      {/* Run detail panel */}
      {selectedRun && (
        <div className="border-t border-[#1E293B] bg-[#0D1321] max-h-[40vh] overflow-y-auto">
          <div className="px-6 py-3 border-b border-[#1E293B] flex items-center justify-between sticky top-0 bg-[#0D1321]">
            <h3 className="text-xs font-medium text-slate-300">
              Run Detail <span className="text-slate-600 font-mono ml-2">{selectedRun.id.slice(0, 8)}</span>
            </h3>
            <div className="flex items-center gap-3 text-[11px]">
              <span className="flex items-center gap-1 text-slate-500"><Hash className="w-3 h-3" />{selectedRun.iterationCount} iter</span>
              <span className={confColor(selectedRun.finalConfidence)}>{(selectedRun.finalConfidence * 100).toFixed(0)}%</span>
            </div>
          </div>
          <div className="px-6 py-3">
            <p className="text-xs text-slate-300 font-mono">{selectedRun.userPrompt}</p>
            <div className="mt-3 space-y-2">
              {selectedRun.iterations.map((iter) => (
                <div key={iter.iteration} className="bg-[#151D2E] border border-[#1E293B] rounded-md p-3">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-[11px] font-medium text-slate-400">Iteration {iter.iteration}</span>
                    <span className={`text-[11px] font-bold ${confColor(iter.synthesis.confidence)}`}>
                      {(iter.synthesis.confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                  <p className="text-[11px] text-slate-500 leading-relaxed line-clamp-3">
                    {iter.synthesis.synthesis}
                  </p>
                  <div className="flex gap-2 mt-2">
                    {iter.modelResponses.slice(0, 4).map((r) => (
                      <span key={r.id} className="text-[10px] px-2 py-0.5 bg-[#0D1321] rounded text-slate-500">
                        {r.model}
                      </span>
                    ))}
                    {iter.modelResponses.length > 4 && (
                      <span className="text-[10px] text-slate-600">+{iter.modelResponses.length - 4}</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
