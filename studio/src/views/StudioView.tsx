import React, { useState, useCallback, useRef } from 'react';
import { useApp } from '@/context/AppContext';
import { ConfigPanel } from '@/components/Config/ConfigPanel';
import { IterationVisualization } from '@/components/Studio/IterationVisualization';
import { ConsortiumConfig, ConsortiumRun, IterationResult } from '@/types';
import { runConsortium, fetchRun } from '@/services/api';

export function StudioView() {
  const { state, dispatch } = useApp();
  const { activeRun, isRunning } = state;

  const [progress, setProgress] = useState(0);
  const [progressMessage, setProgressMessage] = useState('');
  const [outputLines, setOutputLines] = useState<string[]>([]);
  const [liveRun, setLiveRun] = useState<ConsortiumRun | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const handleRun = useCallback(
    async (config: ConsortiumConfig, prompt: string) => {
      dispatch({ type: 'SET_IS_RUNNING', payload: true });
      setProgress(0);
      setProgressMessage('Initializing consortium...');
      setOutputLines([]);
      setLiveRun(null);

      // Clear old poll
      if (pollRef.current) clearInterval(pollRef.current);

      try {
        await runConsortium(
          config.name,
          prompt,
          (text) => {
            setOutputLines(prev => [...prev, text].slice(-100));
            setProgress(p => Math.min(p + 5, 95));
            setProgressMessage('Running...');
          },
          (data) => {
            // iteration data
          },
          async (runId) => {
            setProgress(100);
            setProgressMessage('Complete');
            dispatch({ type: 'SET_IS_RUNNING', payload: false });

            // Fetch the complete run
            try {
              const fullRun = await fetchRun(runId);
              setLiveRun(fullRun);
              dispatch({ type: 'SET_ACTIVE_RUN', payload: fullRun });
              dispatch({ type: 'ADD_RUN_TO_HISTORY', payload: fullRun });
            } catch (e) {
              console.error('Failed to fetch run details:', e);
            }
          }
        );
      } catch (error) {
        console.error('Run failed:', error);
        setProgressMessage('Error: ' + String(error));
        dispatch({ type: 'SET_IS_RUNNING', payload: false });
      }
    },
    [dispatch]
  );

  const displayRun = liveRun || activeRun;

  return (
    <div className="h-full flex">
      {/* Left Panel - Config */}
      <div className="w-[380px] border-r border-[#1E293B] flex-shrink-0">
        <ConfigPanel onRun={handleRun} />
      </div>

      {/* Right Panel - Visualization */}
      <div className="flex-1">
        <IterationVisualization
          run={displayRun}
          isRunning={isRunning}
          progress={progress}
          progressMessage={progressMessage}
          output={outputLines.join('')}
        />
      </div>
    </div>
  );
}
