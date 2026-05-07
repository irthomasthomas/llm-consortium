import React, { useState, useEffect } from 'react';
import { LeaderboardEntry } from '@/types';
import { fetchLeaderboard } from '@/services/api';
import { Trophy, TrendingUp, TrendingDown, Minus, RefreshCw, Hash, Award } from 'lucide-react';

export function LeaderboardView() {
  const [entries, setEntries] = useState<LeaderboardEntry[]>([]);
  const [loading, setLoading] = useState(false);

  const load = async () => {
    setLoading(true);
    try { setEntries(await fetchLeaderboard()); } catch (e) { console.error(e); }
    setLoading(false);
  };

  useEffect(() => { load(); }, []);

  const trendIcon = (trend: string) => {
    if (trend === 'up') return <TrendingUp className="w-3 h-3 text-emerald-400" />;
    if (trend === 'down') return <TrendingDown className="w-3 h-3 text-red-400" />;
    return <Minus className="w-3 h-3 text-slate-600" />;
  };

  return (
    <div className="h-full flex flex-col bg-[#0A0F1A]">
      <div className="px-6 py-4 border-b border-[#1E293B] bg-[#0D1321]">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Model Leaderboard</h2>
            <p className="text-[11px] text-slate-600 mt-0.5">Performance rankings across all consortium runs</p>
          </div>
          <button onClick={load} className="p-2 rounded-md hover:bg-[#1A2332] text-slate-500 hover:text-slate-300 transition-colors">
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {entries.length === 0 && !loading && (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Trophy className="w-10 h-10 text-slate-700 mx-auto mb-3" />
              <p className="text-sm text-slate-500">No leaderboard data yet</p>
              <p className="text-[11px] text-slate-600 mt-1">Run consortiums to populate rankings</p>
            </div>
          </div>
        )}

        <table className="w-full">
          <thead className="sticky top-0 bg-[#0D1321] border-b border-[#1E293B]">
            <tr className="text-[10px] text-slate-500 uppercase tracking-widest">
              <th className="text-left px-6 py-3 font-medium">#</th>
              <th className="text-left px-6 py-3 font-medium">Model</th>
              <th className="text-right px-6 py-3 font-medium">Win Rate</th>
              <th className="text-right px-6 py-3 font-medium">Wins</th>
              <th className="text-right px-6 py-3 font-medium">Runs</th>
              <th className="text-right px-6 py-3 font-medium">Avg Conf</th>
              <th className="text-right px-6 py-3 font-medium">Tokens</th>
              <th className="text-center px-6 py-3 font-medium">Trend</th>
            </tr>
          </thead>
          <tbody>
            {entries.map((entry) => (
              <tr key={entry.modelId}
                className="border-b border-[#1E293B]/30 hover:bg-[#0D1321]/50 transition-colors"
              >
                <td className="px-6 py-3">
                  <div className={`w-6 h-6 rounded-full flex items-center justify-center text-[11px] font-bold data-number ${
                    entry.rank === 1 ? 'bg-amber-500/20 text-amber-400' :
                    entry.rank === 2 ? 'bg-slate-400/20 text-slate-300' :
                    entry.rank === 3 ? 'bg-amber-700/20 text-amber-600' :
                    'text-slate-500'
                  }`}>
                    {entry.rank}
                  </div>
                </td>
                <td className="px-6 py-3">
                  <span className="text-xs font-medium text-slate-300">{entry.modelId}</span>
                </td>
                <td className="px-6 py-3 text-right">
                  <span className="text-xs font-bold text-blue-400 data-number">
                    {(entry.winRate * 100).toFixed(1)}%
                  </span>
                </td>
                <td className="px-6 py-3 text-right">
                  <span className="text-xs text-slate-400 data-number">{entry.wins}</span>
                </td>
                <td className="px-6 py-3 text-right">
                  <span className="text-xs text-slate-500 data-number">{entry.totalRuns}</span>
                </td>
                <td className="px-6 py-3 text-right">
                  <span className="text-xs text-slate-400 data-number">{(entry.avgConfidence * 100).toFixed(1)}%</span>
                </td>
                <td className="px-6 py-3 text-right">
                  <span className="text-xs text-slate-500 data-number">{(entry.totalTokens / 1000).toFixed(0)}k</span>
                </td>
                <td className="px-6 py-3 text-center">{trendIcon(entry.trend)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
