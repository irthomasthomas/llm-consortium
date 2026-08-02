// Real LLM Consortium API Service
// Connects to the Python backend that wraps llm-consortium CLI

import {
  ConsortiumConfig,
  ModelConfig,
  ConsortiumRun,
  IterationResult,
  LeaderboardEntry,
  StrategyParams,
} from '@/types';

const API_BASE = 'http://localhost:8765/api';

// ── Types ──────────────────────────────────────────
interface ServerConsortium {
  name: string;
  strategy?: string;
  models?: string;
  arbiter?: string;
  threshold?: string;
  iterations?: string;
  judging?: string;
  strategy_params?: string;
  created?: string;
}

interface ServerRun {
  id: string;
  created_at: string;
  config_name?: string;
  strategy: string;
  judging_method: string;
  confidence_threshold: number;
  max_iterations: number;
  iteration_count: number;
  final_confidence: number;
  user_prompt: string;
  status?: string;
  category?: string;
  members?: ServerMember[];
  decisions?: ServerDecision[];
}

interface ServerMember {
  consortium_run_id: string;
  model: string;
  instance: number;
  iteration: number;
  response?: string;
  confidence?: number;
  error?: string;
  thinking?: string;
}

interface ServerDecision {
  consortium_run_id: string;
  iteration: number;
  synthesis?: string;
  confidence?: number;
  analysis?: string;
  dissent?: string;
  needs_iteration?: boolean;
  refinement_areas?: string;
  ranking?: string;
}

// ── Helpers ────────────────────────────────────────
async function apiGet<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) throw new Error(`API ${path}: ${res.status}`);
  return res.json();
}

async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(err);
  }
  return res.json();
}

// ── Model Discovery ────────────────────────────────
export async function fetchAvailableModels(): Promise<string[]> {
  const data = await apiGet<{ models: string[] }>('/models');
  return data.models || [];
}

// ── Consortium Configs ─────────────────────────────
export async function fetchConsortiums(): Promise<ConsortiumConfig[]> {
  const data = await apiGet<{ consortiums: ServerConsortium[] }>('/consortiums');
  const configs: ConsortiumConfig[] = (data.consortiums || []).map((c, i) => {
    const modelsStr = c.models || '';
    const modelEntries = modelsStr.split(',').map(m => m.trim()).filter(Boolean);
    const models: ModelConfig[] = modelEntries.map((entry) => {
      const [name, countStr] = entry.split(':');
      return {
        id: name.trim(),
        name: name.trim(),
        instanceCount: parseInt(countStr || '1', 10),
        color: getModelColor(name.trim()),
      };
    });

    const [maxIter, minIter] = (c.iterations || '1-3').split('-').map(Number);

    return {
      id: c.name,
      name: c.name,
      models,
      arbiter: c.arbiter || models[0]?.name || '',
      confidenceThreshold: parseFloat(c.threshold || '0.8'),
      maxIterations: maxIter || 3,
      minIterations: minIter || 1,
      judgingMethod: (c.judging === 'rank' ? 'rank' : 'default') as 'default' | 'rank',
      strategy: (c.strategy || 'default') as ConsortiumConfig['strategy'],
      strategyParams: {},
      manualContext: false,
      createdAt: c.created || new Date().toISOString(),
      updatedAt: c.created || new Date().toISOString(),
    };
  });
  return configs;
}

export async function saveConsortiumConfig(
  name: string,
  models: string[],
  arbiter: string,
  confidenceThreshold: number,
  maxIterations: number,
  minIterations: number,
  strategy: string,
  judgingMethod: string
): Promise<void> {
  await apiPost('/consortiums/save', {
    name,
    models,
    arbiter,
    confidence_threshold: confidenceThreshold,
    max_iterations: maxIterations,
    min_iterations: minIterations,
    strategy,
    judging_method: judgingMethod,
  });
}

export async function deleteConsortium(name: string): Promise<void> {
  await apiPost(`/consortiums/delete?name=${encodeURIComponent(name)}`);
}

// ── Running Consortiums ────────────────────────────
export async function runConsortium(
  configName: string,
  prompt: string,
  onOutput?: (text: string) => void,
  onIteration?: (data: unknown) => void,
  onComplete?: (runId: string) => void
): Promise<void> {
  const res = await fetch(`${API_BASE}/consortiums/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_name: configName, prompt }),
  });

  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n\n');
    buffer = lines.pop() || '';
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (data === '[DONE]') return;
        try {
          const parsed = JSON.parse(data);
          if (parsed.type === 'output') {
            onOutput?.(parsed.text);
          } else if (parsed.type === 'complete') {
            onComplete?.(parsed.run_id);
          }
          onIteration?.(parsed);
        } catch {
          // non-JSON output, forward as text
          onOutput?.(data);
        }
      }
    }
  }
}

// ── Run History ────────────────────────────────────
function parseRunFromServer(sr: ServerRun): ConsortiumRun {
  const iterations: IterationResult[] = [];
  const iterMap = new Map<number, { members: ServerMember[]; decision?: ServerDecision }>();

  for (const m of sr.members || []) {
    if (!iterMap.has(m.iteration)) iterMap.set(m.iteration, { members: [] });
    iterMap.get(m.iteration)!.members.push(m);
  }
  for (const d of sr.decisions || []) {
    if (!iterMap.has(d.iteration)) iterMap.set(d.iteration, { members: [] });
    iterMap.get(d.iteration)!.decision = d;
  }

  for (const [iter, data] of iterMap) {
    const decision = data.decision;
    const ranking = decision?.ranking
      ? JSON.parse(decision.ranking)
      : [];

    iterations.push({
      iteration: iter,
      selectedModels: {},
      modelResponses: data.members.map((m, i) => ({
        id: i + 1,
        model: m.model,
        instance: m.instance || 0,
        response: m.response || m.error || '',
        confidence: m.confidence || 0.5,
        error: m.error,
        timestamp: sr.created_at,
        thinking: m.thinking,
      })),
      synthesis: {
        synthesis: decision?.synthesis || '',
        confidence: decision?.confidence || 0,
        analysis: decision?.analysis || '',
        dissent: decision?.dissent || '',
        needsIteration: decision?.needs_iteration ?? false,
        refinementAreas: decision?.refinement_areas
          ? JSON.parse(decision.refinement_areas)
          : [],
        ranking,
      },
      timestamp: sr.created_at,
      duration: undefined,
    });
  }

  return {
    id: sr.id,
    configName: sr.config_name,
    strategy: sr.strategy || 'default',
    judgingMethod: sr.judging_method || 'default',
    confidenceThreshold: sr.confidence_threshold || 0.8,
    maxIterations: sr.max_iterations || 3,
    iterationCount: sr.iteration_count || iterations.length,
    finalConfidence: sr.final_confidence || 0,
    userPrompt: sr.user_prompt || '',
    createdAt: sr.created_at,
    iterations,
  };
}

export async function fetchRuns(limit = 50): Promise<ConsortiumRun[]> {
  const data = await apiGet<{ runs: ServerRun[] }>(`/runs?limit=${limit}`);
  return (data.runs || []).map(parseRunFromServer);
}

export async function fetchRun(runId: string): Promise<ConsortiumRun> {
  const sr = await apiGet<ServerRun>(`/runs/${runId}`);
  return parseRunFromServer(sr);
}

export function streamRun(
  runId: string,
  onUpdate: (run: ConsortiumRun) => void
): () => void {
  const eventSource = new EventSource(`${API_BASE}/runs/${runId}/stream`);
  eventSource.onmessage = (event) => {
    if (event.data === '[DONE]') {
      eventSource.close();
      return;
    }
    try {
      const sr: ServerRun = JSON.parse(event.data);
      onUpdate(parseRunFromServer(sr));
    } catch {
      // ignore parse errors
    }
  };
  eventSource.onerror = () => eventSource.close();
  return () => eventSource.close();
}

// ── Leaderboard ────────────────────────────────────
export async function fetchLeaderboard(): Promise<LeaderboardEntry[]> {
  const runs = await fetchRuns(200);
  const modelMap = new Map<
    string,
    { totalRuns: number; wins: number; confidences: number[]; tokens: number }
  >();

  for (const run of runs) {
    for (const iter of run.iterations) {
      for (const resp of iter.modelResponses) {
        const key = resp.model;
        if (!modelMap.has(key)) {
          modelMap.set(key, { totalRuns: 0, wins: 0, confidences: [], tokens: 0 });
        }
        const stats = modelMap.get(key)!;
        stats.totalRuns++;
        stats.confidences.push(resp.confidence);
        stats.tokens += resp.response.length;
      }
      if (iter.synthesis.ranking.length > 0) {
        const winnerId = iter.synthesis.ranking[0];
        const winner = iter.modelResponses.find(r => r.id === winnerId);
        if (winner && modelMap.has(winner.model)) {
          modelMap.get(winner.model)!.wins++;
        }
      }
    }
  }

  const entries: LeaderboardEntry[] = [];
  let rank = 0;
  for (const [modelId, stats] of [...modelMap.entries()].sort(
    (a, b) => {
      const wa = a[1].totalRuns > 0 ? a[1].wins / a[1].totalRuns : 0;
      const wb = b[1].totalRuns > 0 ? b[1].wins / b[1].totalRuns : 0;
      return wb - wa;
    }
  )) {
    rank++;
    entries.push({
      rank,
      modelId,
      totalRuns: stats.totalRuns,
      wins: stats.wins,
      winRate: stats.totalRuns > 0 ? stats.wins / stats.totalRuns : 0,
      avgConfidence:
        stats.confidences.length > 0
          ? stats.confidences.reduce((a, b) => a + b, 0) / stats.confidences.length
          : 0,
      avgResponseTime: 0,
      totalTokens: stats.tokens,
      trend: 'stable',
    });
  }
  return entries;
}

// ── Strategies ─────────────────────────────────────
export async function fetchStrategies(): Promise<
  { name: string; description: string }[]
> {
  const data = await apiGet<{ strategies: { name: string; description?: string; class?: string }[] }>('/strategies');
  return (data.strategies || []).map(s => ({
    name: s.name,
    description: s.description || s.class || s.name,
  }));
}

// ── Color helpers ──────────────────────────────────
const MODEL_COLORS = [
  '#3B82F6', '#10B981', '#F59E0B', '#EF4444',
  '#8B5CF6', '#EC4899', '#06B6D4', '#F97316',
  '#6366F1', '#14B8A6', '#D946EF', '#84CC16',
];

function getModelColor(name: string): string {
  let hash = 0;
  for (let i = 0; i < name.length; i++) {
    hash = ((hash << 5) - hash) + name.charCodeAt(i);
    hash |= 0;
  }
  return MODEL_COLORS[Math.abs(hash) % MODEL_COLORS.length];
}

// ── Legacy mock exports (for type compat) ──────────
export const AVAILABLE_MODELS: ModelConfig[] = [];
export const DEFAULT_CONFIGS: ConsortiumConfig[] = [];
export const TASK_CATEGORIES = [];

export function generateMockLeaderboard() {
  return [] as LeaderboardEntry[];
}
export function generateModelStats() {
  return { totalRuns: 0, wins: 0, winRate: 0, avgConfidence: 0, avgResponseTime: 0, totalTokens: 0 };
}

// Legacy stub - real apps should use the actual API functions above
export async function simulateConsortiumRun(
  _config: ConsortiumConfig,
  _prompt: string,
  _onIteration?: (i: IterationResult) => void,
  _onProgress?: (p: number, m: string) => void
): Promise<ConsortiumRun> {
  throw new Error('simulateConsortiumRun is deprecated. Use runConsortium() with real backend.');
}
