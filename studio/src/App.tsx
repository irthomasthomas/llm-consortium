import React from 'react';
import { useApp } from '@/context/AppContext';
import { Sidebar } from '@/components/Layout/Sidebar';
import { StudioView } from '@/views/StudioView';
import { AnalyticsView } from '@/views/AnalyticsView';
import { LeaderboardView } from '@/views/LeaderboardView';
import { LiveEvalView } from '@/views/LiveEvalView';
import { CompareView } from '@/views/CompareView';
import { HistoryView } from '@/views/HistoryView';

function App() {
  const { state } = useApp();
  const { currentView } = state;

  const renderView = () => {
    switch (currentView) {
      case 'studio':
        return <StudioView />;
      case 'analytics':
        return <AnalyticsView />;
      case 'leaderboard':
        return <LeaderboardView />;
      case 'live':
        return <LiveEvalView />;
      case 'compare':
        return <CompareView />;
      case 'history':
        return <HistoryView />;
      default:
        return <StudioView />;
    }
  };

  return (
    <div className="h-screen w-screen flex bg-[#0A0F1A] overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-hidden">
        {renderView()}
      </main>
    </div>
  );
}

export default App;
