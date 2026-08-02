import React, { useState } from 'react';
import { ConsortiumRun, IterationResult, ModelResponse } from '@/types';
import {
  ChevronDown, ChevronRight, Clock, Award, User, Brain,
  MessageSquare, Sparkles, X, Layers, TrendingUp, Hash,
} from 'lucide-react';

interface Props {
  run: ConsortiumRun | null;
  isRunning: boolean;
  progress: number;
  progressMessage: string;
  output?: string;
}

export function IterationVisualization({ run, isRunning, progress, progressMessage, output }: Props) {
  const [selectedResponse, setSelectedResponse] = useState<ModelResponse | null>(null);
  const [expandedIterations, setExpandedIterations] = useState<Set<number>>(new Set());

  // Auto-expand latest iteration
  React.useEffect(() => {
    if (run?.iterations.length) {
      const latest = run.iterations[run.iterations.length - 1].iteration;
      setExpandedIterations(prev => new Set([...prev, latest]));
    }
  }, [run?.iterations.length]);

  if (!run && !isRunning && !output) {
    return (
      <div className="h-full flex items-center justify-center bg-[#0A0F1A]">
        <div className="text-center max-w-md">
          <Layers className="w-12 h-12 text-slate-700 mx-auto mb-4" />
          <h3 className="text-base font-medium text-slate-400 mb-1">Consortium Studio</h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            Configure models, select a strategy, and run a multi-model consortium.
            Responses are synthesized by an arbiter across iterations.
          </p>
        </div>
      </div>
    );
  }

  const toggleIteration = (iter: number) => {
    const next = new Set(expandedIterations);
    next.has(iter) ? next.delete(iter) : next.add(iter);
    setExpandedIterations(next);
  };

  const confColor = (conf: number) => {
    if (conf >= 0.8) return 'text-emerald-400';
    if (conf >= 0.6) return 'text-amber-400';
    return 'text-red-400';
  };

  const confBg = (conf: number) => {
    if (conf >= 0.8) return 'bg-emerald-500/10 border-emerald-500/20';
    if (conf >= 0.6) return 'bg-amber-500/10 border-amber-500/20';
    return 'bg-red-500/10 border-red-500/20';
  };

  return (
    <div className="h-full flex flex-col bg-[#0A0F1A]">
      {/* Progress bar */}
      {isRunning && (
        <div className="px-4 py-2.5 border-b border-[#1E293B] bg-[#0D1321]">
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-[11px] text-slate-500 font-mono">{progressMessage}</span>
            <span className="text-[11px] text-blue-400 font-mono data-number">{progress.toFixed(0)}%</span>
          </div>
          <div className="h-1 bg-[#1A2332] rounded-full overflow-hidden">
            <div className="h-full bg-gradient-to-r from-blue-600 to-blue-400 transition-all duration-500 rounded-full" style={{ width: `${progress}%` }} />
          </div>
        </div>
      )}

      {/* Run header */}
      {run && (
        <div className="px-4 py-3 border-b border-[#1E293B] bg-[#0D1321]">
          <div className="flex items-center justify-between mb-1.5">
            <div className="flex items-center gap-3">
              <h2 className="text-sm font-semibold text-slate-200">
                {run.configName || 'Run'} Results
              </h2>
              <span className="text-[10px] text-slate-600 font-mono">{run.id.slice(0, 8)}</span>
            </div>
            <div className="flex items-center gap-4">
              <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                <Hash className="w-3 h-3" />
                <span className="data-number">{run.iterationCount}/{run.maxIterations}</span>
              </div>
              <div className={`flex items-center gap-1.5 text-[11px] font-medium ${confColor(run.finalConfidence)}`}>
                <Award className="w-3 h-3" />
                <span className="data-number">{(run.finalConfidence * 100).toFixed(0)}%</span>
              </div>
            </div>
          </div>
          <p className="text-[11px] text-slate-500 truncate font-mono">{run.userPrompt}</p>
        </div>
      )}

      {/* Live output stream */}
      {output && (
        <div className="px-4 py-2 border-b border-[#1E293B] bg-[#0D1321]/50 max-h-32 overflow-y-auto">
          <pre className="text-[11px] text-slate-400 font-mono whitespace-pre-wrap">{output}</pre>
        </div>
      )}

      {/* Iterations */}
      <div className="flex-1 overflow-y-auto">
        {run?.iterations.map((iteration) => {
          const isExpanded = expandedIterations.has(iteration.iteration);
          return (
            <div key={iteration.iteration} className="border-b border-[#1E293B]/50">
              {/* Iteration header */}
              <button
                onClick={() => toggleIteration(iteration.iteration)}
                className="w-full flex items-center justify-between px-4 py-3 hover:bg-[#0D1321]/50 transition-colors text-left"
              >
                <div className="flex items-center gap-3">
                  <div className={`w-7 h-7 rounded-full flex items-center justify-center text-[11px] font-bold data-number ${
                    iteration.synthesis.needsIteration
                      ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                      : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                  }`}>
                    {iteration.iteration}
                  </div>
                  <div>
                    <div className="text-xs font-medium text-slate-300">
                      Iteration {iteration.iteration}
                      {iteration.synthesis.needsIteration && (
                        <span className="ml-2 text-[10px] text-amber-500 font-normal">needs iteration</span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 text-[10px] text-slate-600 mt-0.5">
                      <span className="flex items-center gap-1"><User className="w-3 h-3" />{iteration.modelResponses.length}</span>
                      {iteration.duration && <span className="flex items-center gap-1"><Clock className="w-3 h-3" />{iteration.duration}ms</span>}
                    </div>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className={`text-xs font-bold data-number ${confColor(iteration.synthesis.confidence)}`}>
                      {(iteration.synthesis.confidence * 100).toFixed(0)}%
                    </div>
                    <div className="text-[9px] text-slate-600 uppercase tracking-wider">conf</div>
                  </div>
                  {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-600" /> : <ChevronRight className="w-4 h-4 text-slate-600" />}
                </div>
              </button>

              {/* Iteration detail */}
              {isExpanded && (
                <div className="px-4 pb-4 space-y-3">
                  {/* Model Responses */}
                  <div>
                    <h4 className="text-[10px] font-medium text-slate-600 uppercase tracking-widest mb-2">Responses</h4>
                    <div className="space-y-1.5">
                      {iteration.modelResponses.map((response) => (
                        <button
                          key={response.id}
                          onClick={() => setSelectedResponse(response)}
                          className={`w-full text-left p-3 rounded-md border transition-all ${
                            selectedResponse?.id === response.id
                              ? 'border-blue-500/40 bg-blue-500/5'
                              : 'border-[#1E293B] bg-[#0D1321] hover:border-[#2D3A4F]'
                          }`}
                        >
                          <div className="flex items-center justify-between mb-1">
                            <span className="text-xs font-medium text-slate-300">{response.model}</span>
                            <span className={`text-[10px] font-bold data-number ${confColor(response.confidence)}`}>
                              {(response.confidence * 100).toFixed(0)}%
                            </span>
                          </div>
                          <p className="text-[11px] text-slate-500 line-clamp-2 font-mono leading-relaxed">
                            {response.response.substring(0, 200)}
                          </p>
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Synthesis */}
                  {iteration.synthesis.synthesis && (
                    <div className={`p-3 rounded-md border ${confBg(iteration.synthesis.confidence)}`}>
                      <div className="flex items-center gap-2 mb-2">
                        <Sparkles className="w-3.5 h-3.5 text-blue-400" />
                        <span className="text-xs font-medium text-blue-300">Arbiter Synthesis</span>
                      </div>
                      <p className="text-xs text-slate-300 leading-relaxed whitespace-pre-wrap">
                        {iteration.synthesis.synthesis}
                      </p>
                      {iteration.synthesis.analysis && (
                        <div className="mt-2 pt-2 border-t border-slate-700/50">
                          <p className="text-[10px] text-slate-500">{iteration.synthesis.analysis}</p>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Response detail modal */}
      {selectedResponse && (
        <div className="fixed inset-0 bg-black/70 flex items-center justify-center z-50 p-4" onClick={() => setSelectedResponse(null)}>
          <div className="bg-[#151D2E] border border-[#1E293B] rounded-lg w-full max-w-2xl max-h-[80vh] overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="px-4 py-3 border-b border-[#1E293B] flex items-center justify-between">
              <div>
                <h3 className="text-sm font-medium text-slate-200">{selectedResponse.model}</h3>
                <p className="text-[11px] text-slate-500">
                  Confidence: <span className={confColor(selectedResponse.confidence)}>{(selectedResponse.confidence * 100).toFixed(0)}%</span>
                </p>
              </div>
              <button onClick={() => setSelectedResponse(null)} className="p-1.5 hover:bg-[#1A2332] rounded transition-colors">
                <X className="w-4 h-4 text-slate-500" />
              </button>
            </div>
            <div className="p-4 overflow-y-auto max-h-[60vh] space-y-3">
              {selectedResponse.thinking && (
                <div>
                  <h4 className="text-[10px] font-medium text-slate-500 uppercase tracking-widest mb-1.5">Thinking</h4>
                  <div className="p-3 bg-[#0D1321] rounded-md text-xs text-slate-400 font-mono leading-relaxed whitespace-pre-wrap border border-[#1E293B]">
                    {selectedResponse.thinking}
                  </div>
                </div>
              )}
              <div>
                <h4 className="text-[10px] font-medium text-slate-500 uppercase tracking-widest mb-1.5">Response</h4>
                <div className="p-3 bg-[#0D1321] rounded-md text-xs text-slate-300 font-mono leading-relaxed whitespace-pre-wrap border border-[#1E293B]">
                  {selectedResponse.response}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
