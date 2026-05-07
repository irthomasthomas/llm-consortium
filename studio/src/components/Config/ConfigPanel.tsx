import React, { useState, useEffect } from 'react';
import { useApp } from '@/context/AppContext';
import { ConsortiumConfig, ModelConfig } from '@/types';
import {
  fetchConsortiums,
  fetchAvailableModels,
  saveConsortiumConfig,
  deleteConsortium,
  runConsortium,
} from '@/services/api';
import {
  Plus, X, Save, Play, Settings2, ChevronDown, ChevronUp,
  Copy, Check, Trash2, RefreshCw, Cpu, Gavel, Target, Sliders,
} from 'lucide-react';

interface ConfigPanelProps {
  onRun: (config: ConsortiumConfig, prompt: string) => void;
}

const STRATEGIES = [
  { id: 'default', label: 'Default', desc: 'All models respond, arbiter synthesizes' },
  { id: 'voting', label: 'Voting', desc: 'Models vote, consensus wins' },
  { id: 'elimination', label: 'Elimination', desc: 'Weakest models removed each iteration' },
  { id: 'role', label: 'Role-Based', desc: 'Models assigned different cognitive roles' },
];

export function ConfigPanel({ onRun }: ConfigPanelProps) {
  const { state, dispatch } = useApp();
  const { isRunning } = state;

  const [savedConsortiums, setSavedConsortiums] = useState<ConsortiumConfig[]>([]);
  const [availableModels, setAvailableModels] = useState<string[]>([]);
  const [localConfig, setLocalConfig] = useState<ConsortiumConfig>({
    id: '', name: 'New Consortium', models: [], arbiter: '',
    confidenceThreshold: 0.8, maxIterations: 3, minIterations: 1,
    judgingMethod: 'default', strategy: 'default', strategyParams: {},
    manualContext: false, createdAt: '', updatedAt: '',
  });
  const [prompt, setPrompt] = useState('');
  const [showModelPicker, setShowModelPicker] = useState(false);
  const [expandedSection, setExpandedSection] = useState<string>('models');
  const [saveName, setSaveName] = useState('');
  const [showSaveModal, setShowSaveModal] = useState(false);
  const [copied, setCopied] = useState(false);
  const [loading, setLoading] = useState(false);
  const [output, setOutput] = useState('');

  // Load data from backend
  const loadData = async () => {
    setLoading(true);
    try {
      const [configs, models] = await Promise.all([
        fetchConsortiums(),
        fetchAvailableModels(),
      ]);
      setSavedConsortiums(configs);
      setAvailableModels(models);
      if (configs.length > 0 && !localConfig.id) {
        setLocalConfig(configs[0]);
      }
    } catch (e) {
      console.error('Failed to load data:', e);
    }
    setLoading(false);
  };

  useEffect(() => { loadData(); }, []);

  const handleModelToggle = (modelName: string) => {
    const exists = localConfig.models.find(m => m.id === modelName);
    if (exists) {
      setLocalConfig({
        ...localConfig,
        models: localConfig.models.filter(m => m.id !== modelName),
      });
    } else {
      setLocalConfig({
        ...localConfig,
        models: [...localConfig.models, {
          id: modelName, name: modelName, instanceCount: 1,
          color: stringToColor(modelName),
        }],
      });
    }
  };

  const handleInstanceChange = (modelId: string, delta: number) => {
    setLocalConfig({
      ...localConfig,
      models: localConfig.models.map(m =>
        m.id === modelId ? { ...m, instanceCount: Math.max(1, m.instanceCount + delta) } : m
      ),
    });
  };

  const handleSaveConfig = async () => {
    if (!saveName.trim()) return;
    try {
      await saveConsortiumConfig(
        saveName,
        localConfig.models.map(m => `${m.name}:${m.instanceCount}`),
        localConfig.arbiter || localConfig.models[0]?.name || '',
        localConfig.confidenceThreshold,
        localConfig.maxIterations,
        localConfig.minIterations,
        localConfig.strategy,
        localConfig.judgingMethod,
      );
      setShowSaveModal(false);
      setSaveName('');
      loadData();
    } catch (e) {
      console.error('Save failed:', e);
    }
  };

  const handleDeleteConfig = async (name: string) => {
    try {
      await deleteConsortium(name);
      loadData();
    } catch (e) {
      console.error('Delete failed:', e);
    }
  };

  const handleRun = async () => {
    if (!prompt.trim() || localConfig.models.length === 0) return;
    const configName = localConfig.name;
    dispatch({ type: 'SET_IS_RUNNING', payload: true });
    setOutput('');
    try {
      await runConsortium(
        configName,
        prompt,
        (text) => setOutput(prev => prev + text + '\n'),
        undefined,
        (runId) => {
          dispatch({ type: 'SET_IS_RUNNING', payload: false });
          // Trigger parent to load history
        }
      );
      onRun(localConfig, prompt);
    } catch (e) {
      console.error('Run failed:', e);
      dispatch({ type: 'SET_IS_RUNNING', payload: false });
    }
  };

  const copyConfigJson = () => {
    navigator.clipboard.writeText(JSON.stringify(localConfig, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const loadConfig = (config: ConsortiumConfig) => setLocalConfig(config);

  const sections = [
    { id: 'models', label: 'Models', icon: <Cpu className="w-3.5 h-3.5" />, count: localConfig.models.length },
    { id: 'arbiter', label: 'Arbiter', icon: <Gavel className="w-3.5 h-3.5" /> },
    { id: 'strategy', label: 'Strategy', icon: <Target className="w-3.5 h-3.5" /> },
    { id: 'thresholds', label: 'Parameters', icon: <Sliders className="w-3.5 h-3.5" /> },
  ];

  return (
    <div className="h-full flex flex-col bg-[#0D1321]">
      {/* Header */}
      <div className="px-4 py-3 border-b border-[#1E293B]">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-sm font-semibold text-slate-200 uppercase tracking-wider">Configuration</h2>
          <button onClick={loadData} className="p-1.5 rounded hover:bg-[#1A2332] text-slate-500 hover:text-slate-300 transition-colors">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        {/* Saved configs */}
        <div className="flex gap-1.5 overflow-x-auto pb-1">
          {savedConsortiums.slice(0, 6).map((config) => (
            <div key={config.id} className="group relative flex-shrink-0">
              <button
                onClick={() => loadConfig(config)}
                className={`px-3 py-1.5 rounded text-[11px] whitespace-nowrap transition-all ${
                  localConfig.id === config.id
                    ? 'bg-blue-600/30 text-blue-400 border border-blue-500/30'
                    : 'bg-[#1A2332] text-slate-400 hover:text-slate-200 border border-transparent hover:border-[#2D3A4F]'
                }`}
              >
                {config.name}
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleDeleteConfig(config.name); }}
                className="absolute -top-1 -right-1 w-4 h-4 rounded-full bg-red-500/80 text-white hidden group-hover:flex items-center justify-center"
              >
                <X className="w-2.5 h-2.5" />
              </button>
            </div>
          ))}
          {savedConsortiums.length === 0 && !loading && (
            <span className="text-xs text-slate-600 italic py-1.5">No saved consortiums</span>
          )}
        </div>
      </div>

      {/* Config Sections */}
      <div className="flex-1 overflow-y-auto px-3 py-2 space-y-1.5">
        {/* Models */}
        <div className="rounded-lg bg-[#151D2E] border border-[#1E293B] overflow-hidden">
          <button
            onClick={() => setExpandedSection(expandedSection === 'models' ? null : 'models')}
            className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-[#1A2332]/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Cpu className="w-3.5 h-3.5 text-blue-400" />
              <span className="text-xs font-medium text-slate-300">Models</span>
              <span className="text-[10px] text-slate-500 bg-[#1A2332] px-1.5 py-0.5 rounded">
                {localConfig.models.length}
              </span>
            </div>
            {expandedSection === 'models' ? <ChevronUp className="w-3.5 h-3.5 text-slate-500" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />}
          </button>
          {expandedSection === 'models' && (
            <div className="px-3 pb-3 space-y-2">
              {localConfig.models.map((model) => (
                <div key={model.id} className="flex items-center justify-between bg-[#0D1321] rounded-md px-2.5 py-2 border border-[#1E293B]">
                  <div className="flex items-center gap-2 min-w-0">
                    <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ backgroundColor: model.color }} />
                    <span className="text-xs text-slate-300 truncate">{model.name}</span>
                  </div>
                  <div className="flex items-center gap-1 flex-shrink-0">
                    <button onClick={() => handleInstanceChange(model.id, -1)} className="w-5 h-5 rounded text-slate-500 hover:text-white hover:bg-[#2D3A4F] text-xs">−</button>
                    <span className="w-4 text-center text-xs text-slate-400 data-number">{model.instanceCount}</span>
                    <button onClick={() => handleInstanceChange(model.id, 1)} className="w-5 h-5 rounded text-slate-500 hover:text-white hover:bg-[#2D3A4F] text-xs">+</button>
                    <button onClick={() => handleModelToggle(model.name)} className="w-5 h-5 rounded text-slate-600 hover:text-red-400 hover:bg-red-500/10 ml-0.5"><X className="w-3 h-3" /></button>
                  </div>
                </div>
              ))}
              <button
                onClick={() => setShowModelPicker(!showModelPicker)}
                className="w-full py-2 border border-dashed border-[#2D3A4F] rounded-md text-xs text-slate-500 hover:text-slate-300 hover:border-slate-500 transition-colors"
              >
                <Plus className="w-3.5 h-3.5 inline mr-1" /> Add Model
              </button>
              {showModelPicker && (
                <div className="bg-[#0D1321] border border-[#1E293B] rounded-md p-1.5 max-h-36 overflow-y-auto space-y-0.5">
                  {availableModels
                    .filter(m => !localConfig.models.find(cm => cm.id === m))
                    .map((model) => (
                      <button
                        key={model}
                        onClick={() => { handleModelToggle(model); setShowModelPicker(false); }}
                        className="w-full text-left px-2.5 py-1.5 rounded text-xs text-slate-400 hover:text-slate-200 hover:bg-[#1A2332] transition-colors"
                      >
                        {model}
                      </button>
                    ))}
                  {availableModels.length === 0 && (
                    <div className="text-xs text-slate-600 px-2.5 py-2">
                      No models available. Is the backend running?
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Arbiter */}
        <div className="rounded-lg bg-[#151D2E] border border-[#1E293B] overflow-hidden">
          <button
            onClick={() => setExpandedSection(expandedSection === 'arbiter' ? null : 'arbiter')}
            className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-[#1A2332]/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Gavel className="w-3.5 h-3.5 text-amber-400" />
              <span className="text-xs font-medium text-slate-300">Arbiter</span>
            </div>
            {expandedSection === 'arbiter' ? <ChevronUp className="w-3.5 h-3.5 text-slate-500" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />}
          </button>
          {expandedSection === 'arbiter' && (
            <div className="px-3 pb-3 space-y-2">
              <select
                value={localConfig.arbiter}
                onChange={(e) => setLocalConfig({ ...localConfig, arbiter: e.target.value })}
                className="w-full bg-[#0D1321] border border-[#1E293B] rounded-md px-2.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500/50"
              >
                <option value="">Auto-select</option>
                {(localConfig.models.length > 0 ? localConfig.models : availableModels.map(m => ({ id: m, name: m }))).map((m) => (
                  <option key={m.id || m} value={m.name || m}>{m.name || m}</option>
                ))}
              </select>
              <div className="flex gap-1.5">
                {['default', 'rank'].map((method) => (
                  <button
                    key={method}
                    onClick={() => setLocalConfig({ ...localConfig, judgingMethod: method as 'default' | 'rank' })}
                    className={`flex-1 py-1.5 rounded text-[11px] transition-all ${
                      localConfig.judgingMethod === method
                        ? 'bg-blue-600/30 text-blue-400 border border-blue-500/30'
                        : 'bg-[#0D1321] text-slate-500 hover:text-slate-300 border border-[#1E293B]'
                    }`}
                  >
                    {method === 'default' ? 'Synthesis' : 'Ranking'}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Strategy */}
        <div className="rounded-lg bg-[#151D2E] border border-[#1E293B] overflow-hidden">
          <button
            onClick={() => setExpandedSection(expandedSection === 'strategy' ? null : 'strategy')}
            className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-[#1A2332]/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Target className="w-3.5 h-3.5 text-emerald-400" />
              <span className="text-xs font-medium text-slate-300">Strategy</span>
            </div>
            {expandedSection === 'strategy' ? <ChevronUp className="w-3.5 h-3.5 text-slate-500" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />}
          </button>
          {expandedSection === 'strategy' && (
            <div className="px-3 pb-3 space-y-2">
              <div className="grid grid-cols-2 gap-1.5">
                {STRATEGIES.map((s) => (
                  <button
                    key={s.id}
                    onClick={() => setLocalConfig({ ...localConfig, strategy: s.id as ConsortiumConfig['strategy'] })}
                    className={`py-2 rounded text-[11px] transition-all ${
                      localConfig.strategy === s.id
                        ? 'bg-blue-600/30 text-blue-400 border border-blue-500/30'
                        : 'bg-[#0D1321] text-slate-500 hover:text-slate-300 border border-[#1E293B]'
                    }`}
                  >
                    {s.label}
                  </button>
                ))}
              </div>
              <p className="text-[10px] text-slate-600 leading-relaxed">
                {STRATEGIES.find(s => s.id === localConfig.strategy)?.desc}
              </p>
            </div>
          )}
        </div>

        {/* Parameters */}
        <div className="rounded-lg bg-[#151D2E] border border-[#1E293B] overflow-hidden">
          <button
            onClick={() => setExpandedSection(expandedSection === 'thresholds' ? null : 'thresholds')}
            className="w-full flex items-center justify-between px-3 py-2.5 hover:bg-[#1A2332]/50 transition-colors"
          >
            <div className="flex items-center gap-2">
              <Sliders className="w-3.5 h-3.5 text-purple-400" />
              <span className="text-xs font-medium text-slate-300">Parameters</span>
            </div>
            {expandedSection === 'thresholds' ? <ChevronUp className="w-3.5 h-3.5 text-slate-500" /> : <ChevronDown className="w-3.5 h-3.5 text-slate-500" />}
          </button>
          {expandedSection === 'thresholds' && (
            <div className="px-3 pb-3 space-y-3">
              <div>
                <div className="flex justify-between text-[10px] text-slate-500 mb-1">
                  <span>Confidence Threshold</span>
                  <span className="data-number text-blue-400">{(localConfig.confidenceThreshold * 100).toFixed(0)}%</span>
                </div>
                <input
                  type="range" min="0" max="100"
                  value={localConfig.confidenceThreshold * 100}
                  onChange={(e) => setLocalConfig({ ...localConfig, confidenceThreshold: parseInt(e.target.value) / 100 })}
                  className="w-full h-1.5 bg-[#1A2332] rounded-full appearance-none cursor-pointer [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3 [&::-webkit-slider-thumb]:h-3 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-blue-500"
                />
              </div>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] text-slate-500 block mb-1">Min Iterations</label>
                  <input type="number" min="1" max="10" value={localConfig.minIterations}
                    onChange={(e) => setLocalConfig({ ...localConfig, minIterations: parseInt(e.target.value) || 1 })}
                    className="w-full bg-[#0D1321] border border-[#1E293B] rounded-md px-2.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500/50 data-number"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 block mb-1">Max Iterations</label>
                  <input type="number" min="1" max="10" value={localConfig.maxIterations}
                    onChange={(e) => setLocalConfig({ ...localConfig, maxIterations: parseInt(e.target.value) || 1 })}
                    className="w-full bg-[#0D1321] border border-[#1E293B] rounded-md px-2.5 py-2 text-xs text-slate-200 focus:outline-none focus:border-blue-500/50 data-number"
                  />
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Bottom: Prompt + Actions */}
      <div className="px-4 py-3 border-t border-[#1E293B] space-y-2">
        <textarea
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          placeholder="Enter your prompt..."
          className="w-full h-20 bg-[#0D1321] border border-[#1E293B] rounded-md px-3 py-2 text-xs text-slate-200 placeholder-slate-600 resize-none focus:outline-none focus:border-blue-500/50 font-mono"
        />
        <div className="flex gap-2">
          <button
            onClick={() => setShowSaveModal(true)}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-[#1A2332] text-slate-300 rounded-md hover:bg-[#243049] text-xs transition-colors border border-[#1E293B]"
          >
            <Save className="w-3.5 h-3.5" /> Save
          </button>
          <button
            onClick={handleRun}
            disabled={!prompt.trim() || localConfig.models.length === 0 || isRunning}
            className="flex-1 flex items-center justify-center gap-1.5 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed text-xs font-medium transition-colors"
          >
            {isRunning ? (
              <><RefreshCw className="w-3.5 h-3.5 animate-spin" /> Running...</>
            ) : (
              <><Play className="w-3.5 h-3.5" /> Run Consortium</>
            )}
          </button>
        </div>
      </div>

      {/* Save Modal */}
      {showSaveModal && (
        <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
          <div className="bg-[#151D2E] border border-[#1E293B] rounded-lg p-4 w-80 shadow-2xl">
            <h3 className="text-sm font-medium text-slate-200 mb-3">Save Configuration</h3>
            <input
              type="text" value={saveName} onChange={(e) => setSaveName(e.target.value)}
              placeholder="Configuration name..."
              className="w-full bg-[#0D1321] border border-[#1E293B] rounded-md px-3 py-2 text-xs text-slate-200 placeholder-slate-600 mb-3 focus:outline-none focus:border-blue-500/50"
              autoFocus
            />
            <div className="flex gap-2">
              <button onClick={() => setShowSaveModal(false)} className="flex-1 py-2 bg-[#1A2332] text-slate-400 rounded-md hover:bg-[#243049] text-xs transition-colors">Cancel</button>
              <button onClick={handleSaveConfig} disabled={!saveName.trim()} className="flex-1 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-500 text-xs disabled:opacity-40 transition-colors">Save</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

function stringToColor(str: string): string {
  const colors = ['#3B82F6', '#10B981', '#F59E0B', '#EF4444', '#8B5CF6', '#EC4899', '#06B6D4', '#F97316'];
  let hash = 0;
  for (let i = 0; i < str.length; i++) { hash = ((hash << 5) - hash) + str.charCodeAt(i); hash |= 0; }
  return colors[Math.abs(hash) % colors.length];
}
