// Core types for LLM Consortium Studio

export interface ModelConfig {
  id: string;
  name: string;
  instanceCount: number;
  color: string;
  icon?: string;
}

export interface ConsortiumConfig {
  id: string;
  name: string;
  models: ModelConfig[];
  arbiter: string;
  confidenceThreshold: number;
  maxIterations: number;
  minIterations: number;
  judgingMethod: 'default' | 'rank';
  strategy: 'default' | 'voting' | 'elimination' | 'role';
  strategyParams: Record<string, any>;
  manualContext: boolean;
  systemPrompt?: string;
  createdAt: string;
  updatedAt: string;
}

export interface ModelResponse {
  id: number;
  model: string;
  instance: number;
  response: string;
  confidence: number;
  error?: string;
  timestamp: string;
  thinking?: string;
  votingMetadata?: {
    selected: boolean;
    groupSize: number;
    total: number;
    similarity?: number;
  };
}

export interface ArbiterDecision {
  synthesis: string;
  confidence: number;
  analysis: string;
  dissent: string;
  needsIteration: boolean;
  refinementAreas: string[];
  ranking: number[];
  rawResponse?: string;
  chosenResponseId?: number;
}

export interface IterationResult {
  iteration: number;
  selectedModels: Record<string, number>;
  modelResponses: ModelResponse[];
  synthesis: ArbiterDecision;
  timestamp: string;
  duration?: number;
  tokenUsage?: {
    total: number;
    byModel: Record<string, number>;
  };
}

export interface ConsortiumRun {
  id: string;
  configName?: string;
  strategy: string;
  judgingMethod: string;
  confidenceThreshold: number;
  maxIterations: number;
  iterationCount: number;
  finalConfidence: number;
  userPrompt: string;
  createdAt: string;
  iterations: IterationResult[];
}

export interface StrategyParams {
  voting?: {
    similarityThreshold: number;
    answerLength: number;
    requireMajority: boolean;
    fallbackToAll: boolean;
  };
  elimination?: {
    eliminateCount: number;
    eliminateFraction: number;
    keepMinimum: number;
    eliminationDelay: number;
  };
  role?: {
    roles: string[];
    useDynamicPersonalities: boolean;
  };
}

export interface ModelStats {
  modelId: string;
  totalRuns: number;
  wins: number;
  winRate: number;
  avgConfidence: number;
  avgResponseTime: number;
  totalTokens: number;
  eliminationRank?: number;
  lastAppearance?: string;
}

export interface LeaderboardEntry extends ModelStats {
  rank: number;
  trend: 'up' | 'down' | 'stable';
  previousRank?: number;
}

export interface TaskCategory {
  id: string;
  name: string;
  description: string;
  icon: string;
  benchmarks: Benchmark[];
}

export interface Benchmark {
  id: string;
  name: string;
  description: string;
  difficulty: 'easy' | 'medium' | 'hard' | 'expert';
  category: string;
  prompt: string;
  expectedCapabilities: string[];
}

export interface LiveEvaluation {
  id: string;
  prompt: string;
  category: string;
  consortiumId: string;
  status: 'pending' | 'running' | 'completed' | 'failed';
  startTime?: string;
  endTime?: string;
  results?: ConsortiumRun;
  metrics?: EvaluationMetrics;
}

export interface EvaluationMetrics {
  accuracy?: number;
  coherence?: number;
  creativity?: number;
  factuality?: number;
  helpfulness?: number;
  overallScore: number;
  breakdown: Record<string, number>;
  comparisonData?: {
    modelScores: Record<string, number>;
    consensusScore: number;
  };
}

export interface VisualizationData {
  iteration: number;
  confidence: number;
  modelRankings: { model: string; rank: number; score: number }[];
  tokenUsage: number;
  convergenceRate: number;
}

export interface ComparisonRun {
  id: string;
  prompt: string;
  strategies: string[];
  results: Record<string, ConsortiumRun>;
  timestamp: string;
}

export type ViewMode = 'studio' | 'analytics' | 'leaderboard' | 'live' | 'compare' | 'history';
export type ThemeMode = 'light' | 'dark' | 'system';
