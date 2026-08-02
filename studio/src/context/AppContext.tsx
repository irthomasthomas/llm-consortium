import React, { createContext, useContext, useReducer, ReactNode } from 'react';
import {
  ConsortiumConfig,
  ConsortiumRun,
  LeaderboardEntry,
  ModelStats,
  ViewMode,
  ThemeMode,
  StrategyParams,
  ComparisonRun,
} from '@/types';

interface AppState {
  // View state
  currentView: ViewMode;
  theme: ThemeMode;
  sidebarCollapsed: boolean;

  // Consortium configurations
  savedConfigs: ConsortiumConfig[];
  activeConfig: ConsortiumConfig | null;

  // Active runs
  activeRun: ConsortiumRun | null;
  runHistory: ConsortiumRun[];

  // Leaderboard
  leaderboard: LeaderboardEntry[];
  modelStats: Record<string, ModelStats>;

  // Comparison
  comparisonRuns: ComparisonRun[];

  // UI state
  isRunning: boolean;
  showConfigModal: boolean;
  showExportModal: boolean;

  // Strategy params
  strategyParams: StrategyParams;
}

type AppAction =
  | { type: 'SET_VIEW'; payload: ViewMode }
  | { type: 'SET_THEME'; payload: ThemeMode }
  | { type: 'TOGGLE_SIDEBAR' }
  | { type: 'SET_SAVED_CONFIGS'; payload: ConsortiumConfig[] }
  | { type: 'ADD_SAVED_CONFIG'; payload: ConsortiumConfig }
  | { type: 'UPDATE_SAVED_CONFIG'; payload: ConsortiumConfig }
  | { type: 'DELETE_SAVED_CONFIG'; payload: string }
  | { type: 'SET_ACTIVE_CONFIG'; payload: ConsortiumConfig | null }
  | { type: 'SET_ACTIVE_RUN'; payload: ConsortiumRun | null }
  | { type: 'ADD_RUN_TO_HISTORY'; payload: ConsortiumRun }
  | { type: 'SET_RUN_HISTORY'; payload: ConsortiumRun[] }
  | { type: 'UPDATE_LEADERBOARD'; payload: LeaderboardEntry[] }
  | { type: 'UPDATE_MODEL_STATS'; payload: Record<string, ModelStats> }
  | { type: 'ADD_COMPARISON_RUN'; payload: ComparisonRun }
  | { type: 'SET_IS_RUNNING'; payload: boolean }
  | { type: 'SET_SHOW_CONFIG_MODAL'; payload: boolean }
  | { type: 'SET_SHOW_EXPORT_MODAL'; payload: boolean }
  | { type: 'UPDATE_STRATEGY_PARAMS'; payload: StrategyParams };

const initialState: AppState = {
  currentView: 'studio',
  theme: 'dark',
  sidebarCollapsed: false,
  savedConfigs: [],
  activeConfig: null,
  activeRun: null,
  runHistory: [],
  leaderboard: [],
  modelStats: {},
  comparisonRuns: [],
  isRunning: false,
  showConfigModal: false,
  showExportModal: false,
  strategyParams: {},
};

function appReducer(state: AppState, action: AppAction): AppState {
  switch (action.type) {
    case 'SET_VIEW':
      return { ...state, currentView: action.payload };
    case 'SET_THEME':
      return { ...state, theme: action.payload };
    case 'TOGGLE_SIDEBAR':
      return { ...state, sidebarCollapsed: !state.sidebarCollapsed };
    case 'SET_SAVED_CONFIGS':
      return { ...state, savedConfigs: action.payload };
    case 'ADD_SAVED_CONFIG':
      return { ...state, savedConfigs: [...state.savedConfigs, action.payload] };
    case 'UPDATE_SAVED_CONFIG':
      return {
        ...state,
        savedConfigs: state.savedConfigs.map((c) =>
          c.id === action.payload.id ? action.payload : c
        ),
      };
    case 'DELETE_SAVED_CONFIG':
      return {
        ...state,
        savedConfigs: state.savedConfigs.filter((c) => c.id !== action.payload),
      };
    case 'SET_ACTIVE_CONFIG':
      return { ...state, activeConfig: action.payload };
    case 'SET_ACTIVE_RUN':
      return { ...state, activeRun: action.payload };
    case 'ADD_RUN_TO_HISTORY':
      return { ...state, runHistory: [action.payload, ...state.runHistory].slice(0, 100) };
    case 'SET_RUN_HISTORY':
      return { ...state, runHistory: action.payload };
    case 'UPDATE_LEADERBOARD':
      return { ...state, leaderboard: action.payload };
    case 'UPDATE_MODEL_STATS':
      return { ...state, modelStats: action.payload };
    case 'ADD_COMPARISON_RUN':
      return { ...state, comparisonRuns: [...state.comparisonRuns, action.payload] };
    case 'SET_IS_RUNNING':
      return { ...state, isRunning: action.payload };
    case 'SET_SHOW_CONFIG_MODAL':
      return { ...state, showConfigModal: action.payload };
    case 'SET_SHOW_EXPORT_MODAL':
      return { ...state, showExportModal: action.payload };
    case 'UPDATE_STRATEGY_PARAMS':
      return { ...state, strategyParams: action.payload };
    default:
      return state;
  }
}

interface AppContextType {
  state: AppState;
  dispatch: React.Dispatch<AppAction>;
}

const AppContext = createContext<AppContextType | undefined>(undefined);

export function AppProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(appReducer, initialState);

  return (
    <AppContext.Provider value={{ state, dispatch }}>
      {children}
    </AppContext.Provider>
  );
}

export function useApp() {
  const context = useContext(AppContext);
  if (context === undefined) {
    throw new Error('useApp must be used within an AppProvider');
  }
  return context;
}

export function useConsortium() {
  const { state, dispatch } = useApp();

  const startRun = (config: ConsortiumConfig, prompt: string) => {
    dispatch({ type: 'SET_IS_RUNNING', payload: true });
    dispatch({ type: 'SET_ACTIVE_CONFIG', payload: config });

    // Create initial run structure
    const run: ConsortiumRun = {
      id: crypto.randomUUID(),
      configName: config.name,
      strategy: config.strategy,
      judgingMethod: config.judgingMethod,
      confidenceThreshold: config.confidenceThreshold,
      maxIterations: config.maxIterations,
      iterationCount: 0,
      finalConfidence: 0,
      userPrompt: prompt,
      createdAt: new Date().toISOString(),
      iterations: [],
    };

    dispatch({ type: 'SET_ACTIVE_RUN', payload: run });
  };

  const completeRun = (run: ConsortiumRun) => {
    dispatch({ type: 'SET_IS_RUNNING', payload: false });
    dispatch({ type: 'ADD_RUN_TO_HISTORY', payload: run });
  };

  return {
    ...state,
    startRun,
    completeRun,
  };
}
