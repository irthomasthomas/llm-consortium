import React, { useState, useEffect } from 'react';
import { fetchRuns } from '@/services/api';
import { ConsortiumRun } from '@/types';
import { BarChart3, RefreshCw, TrendingUp, Hash, Activity } from 'lucide-react';

export function AnalyticsView() {
  const [runs, setRuns] = useState<ConsortiumRun[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setRuns(await fetchRuns(100)); } catch (e) { console.error(e); }
    setLoading(false);
  };
  useEffect(() => { load(); }, []);

  // Aggregate stats
  const totalRuns = runs.length;
  const avgConfidence = runs.length > 0
    ? runs.reduce((a, r) => a + r.finalConfidence, 0) / runs.length
    : 0;
  const avgIterations = runs.length > 0
    ? runs.reduce((a, r) => a + r.iterationCount, 0) / runs.length
    : 0;
  const strategies = new Map<string, number>();
  runs.forEach(r => strategies.set(r.strategy, (strategies.get(r.strategy) || 0) + 1));

  return (
    <div className="h-full flex flex-col bg-[#0A0F1A]">
      <div className="px-6 py-4 border-b border-[#1E293B] bg-[#0D1321]">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Analytics</h2>
            <p className="text-[11px] text-slate-600 mt-0.5">Aggregate metrics across all consortium runs</p>
          </div>
          <button onClick={load} className="p-2 rounded-md hover:bg-[#1A2332] text-slate-500 hover:text-slate-300">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        {runs.length === 0 ? (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <BarChart3 className="w-10 h-10 text-slate-700 mx-auto mb-3" />
              <p className="text-sm text-slate-500">No data yet</p>
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {/* KPI cards */}
            <div className="grid grid-cols-4 gap-4">
              {[
                { label: 'Total Runs', value: totalRuns, icon: <Hash className="w-4 h-4" />, color: 'text-blue-400' },
                { label: 'Avg Confidence', value: `${(avgConfidence * 100).toFixed(1)}%`, icon: <TrendingUp className="w-4 h-4" />, color: 'text-emerald-400' },
                { label: 'Avg Iterations', value: avgIterations.toFixed(1), icon: <Activity className="w-4 h-4" />, color: 'text-amber-400' },
                { label: 'Strategies Used', value: strategies.size, icon: <BarChart3 className="w-4 h-4" />, color: 'text-purple-400' },
              ].map((kpi) => (
                <div key={kpi.label} className="bg-[#151D2E] border border-[#1E293B] rounded-lg p-4">
                  <div className="flex items-center gap-2 mb-2">
                    <span className={kpi.color}>{kpi.icon}</span>
                    <span className="text-[10px] text-slate-500 uppercase tracking-widest">{kpi.label}</span>
                  </div>
                  <div className={`text-2xl font-bold data-number ${kpi.color}`}>{kpi.value}</div>
                </div>
              ))}
            </div>

            {/* Strategy breakdown */}
            <div className="bg-[#151D2E] border border-[#1E293B] rounded-lg p-4">
              <h3 className="text-xs font-medium text-slate-300 mb-3 uppercase tracking-wider">Strategy Usage</h3>
              <div className="space-y-2">
                {[...strategies.entries()].sort((a, b) => b[1] - a[1]).map(([strategy, count]) => (
                  <div key={strategy} className="flex items-center gap-3">
                    <span className="text-xs text-slate-400 w-24">{strategy}</span>
                    <div className="flex-1 h-4 bg-[#0D1321] rounded-full overflow-hidden">
                      <div
                        className="h-full bg-blue-600/60 rounded-full transition-all"
                        style={{ width: `${(count / totalRuns) * 100}%` }}
                      />
                    </div>
                    <span className="text-xs text-slate-500 data-number w-8 text-right">{count}</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Recent runs table */}
            <div className="bg-[#151D2E] border border-[#1E293B] rounded-lg overflow-hidden">
              <h3 className="text-xs font-medium text-slate-300 p-4 border-b border-[#1E293B] uppercase tracking-wider">Recent Runs</h3>
              <table className="w-full">
                <thead>
                  <tr className="text-[10px] text-slate-500 uppercase tracking-widest border-b border-[#1E293B]">
                    <th className="text-left px-4 py-2">Prompt</th>
                    <th className="text-left px-4 py-2">Strategy</th>
                    <th className="text-right px-4 py-2">Conf</th>
                    <th className="text-right px-4 py-2">Iters</th>
                    <th className="text-right px-4 py-2">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {runs.slice(0, 20).map(run => (
                    <tr key={run.id} className="border-b border-[#1E293B]/30 text-xs">
                      <td className="px-4 py-2 text-slate-400 truncate max-w-xs">{run.userPrompt}</td>
                      <td className="px-4 py-2 text-slate-500">{run.strategy}</td>
                      <td className="px-4 py-2 text-right text-slate-300 data-number">{(run.finalConfidence * 100).toFixed(0)}%</td>
                      <td className="px-4 py-2 text-right text-slate-500 data-number">{run.iterationCount}</td>
                      <td className="px-4 py-2 text-right text-slate-600">{new Date(run.createdAt).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
