import React from 'react';
import { useApp } from '@/context/AppContext';
import { ViewMode } from '@/types';
import {
  LayoutDashboard,
  Brain,
  Trophy,
  Zap,
  GitCompare,
  History,
  Settings,
  ChevronLeft,
  ChevronRight,
  Hexagon,
} from 'lucide-react';

interface NavItem {
  id: ViewMode;
  label: string;
  icon: React.ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { id: 'studio', label: 'Studio', icon: <LayoutDashboard className="w-4 h-4" /> },
  { id: 'analytics', label: 'Analytics', icon: <Brain className="w-4 h-4" /> },
  { id: 'leaderboard', label: 'Leaderboard', icon: <Trophy className="w-4 h-4" /> },
  { id: 'live', label: 'Live Eval', icon: <Zap className="w-4 h-4" /> },
  { id: 'compare', label: 'Compare', icon: <GitCompare className="w-4 h-4" /> },
  { id: 'history', label: 'History', icon: <History className="w-4 h-4" /> },
];

export function Sidebar() {
  const { state, dispatch } = useApp();
  const { currentView, sidebarCollapsed } = state;

  return (
    <aside
      className={`h-screen flex flex-col transition-all duration-200 bg-[#0D1321] border-r border-[#1E293B] ${
        sidebarCollapsed ? 'w-[56px]' : 'w-[220px]'
      }`}
    >
      {/* Logo area */}
      <div className="h-14 flex items-center px-3 border-b border-[#1E293B]">
        {sidebarCollapsed ? (
          <div className="mx-auto w-7 h-7 rounded bg-gradient-to-br from-blue-600 to-blue-400 flex items-center justify-center">
            <Hexagon className="w-4 h-4 text-white" />
          </div>
        ) : (
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded bg-gradient-to-br from-blue-600 to-blue-400 flex items-center justify-center flex-shrink-0">
              <Hexagon className="w-4 h-4 text-white" />
            </div>
            <div className="leading-tight">
              <div className="text-xs font-semibold text-slate-100 tracking-tight">CONSORTIUM</div>
              <div className="text-[10px] text-slate-500 font-medium tracking-widest uppercase">Studio</div>
            </div>
          </div>
        )}
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 space-y-0.5">
        {NAV_ITEMS.map((item) => {
          const isActive = currentView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => dispatch({ type: 'SET_VIEW', payload: item.id })}
              className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm transition-all duration-150 ${
                isActive
                  ? 'bg-blue-600/20 text-blue-400 font-medium border-l-[3px] border-blue-500 pl-[9px]'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-[#1A2332] border-l-[3px] border-transparent pl-[9px]'
              } ${sidebarCollapsed ? 'justify-center pl-3' : ''}`}
              title={sidebarCollapsed ? item.label : undefined}
            >
              {item.icon}
              {!sidebarCollapsed && <span>{item.label}</span>}
            </button>
          );
        })}
      </nav>

      {/* Bottom */}
      <div className="border-t border-[#1E293B] p-2">
        <button
          onClick={() => dispatch({ type: 'TOGGLE_SIDEBAR' })}
          className="w-full flex items-center justify-center gap-2 px-3 py-2 rounded-md text-slate-500 hover:text-slate-300 hover:bg-[#1A2332] transition-all duration-150 text-xs"
        >
          {sidebarCollapsed ? <ChevronRight className="w-4 h-4" /> : (
            <>
              <ChevronLeft className="w-4 h-4" />
              <span>Collapse</span>
            </>
          )}
        </button>
        <button
          className={`w-full flex items-center gap-2 px-3 py-2 rounded-md text-slate-500 hover:text-slate-300 hover:bg-[#1A2332] transition-all duration-150 text-xs mt-0.5 ${
            sidebarCollapsed ? 'justify-center' : ''
          }`}
        >
          <Settings className="w-4 h-4" />
          {!sidebarCollapsed && <span>Settings</span>}
        </button>
      </div>
    </aside>
  );
}
