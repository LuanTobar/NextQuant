'use client';

import { PortfolioHealth } from './PortfolioHealth';
import { PositionsView } from './PositionsView';
import { ChatInterface } from './ChatInterface';
import { SwipeToInvest } from './SwipeToInvest';
import { TradeHistory } from './TradeHistory';
import { ClaudeInsights } from './ClaudeInsights';
import { LiveSignalFeed } from './LiveSignalFeed';
import { AgentStatusWidget } from './AgentStatusWidget';

export function Dashboard() {
  return (
    <div className="flex flex-col gap-4 p-4 max-w-[1600px] mx-auto">
      {/* Agent status bar — full width */}
      <AgentStatusWidget />

      {/* Main grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-4">
        {/* Mobile: SwipeToInvest first for engagement */}
        <div className="lg:hidden space-y-4">
          <SwipeToInvest />
        </div>

        {/* Left: Portfolio + Positions + Trade History */}
        <div className="lg:col-span-4 space-y-4">
          <PortfolioHealth />
          <PositionsView />
          <TradeHistory />
        </div>

        {/* Center: Live Signal Feed + Claude Intelligence */}
        <div className="lg:col-span-4 space-y-4">
          <div className="hidden lg:block">
            <SwipeToInvest />
          </div>
          <LiveSignalFeed />
          <ClaudeInsights />
        </div>

        {/* Right: Chat */}
        <div className="lg:col-span-4">
          <ChatInterface />
        </div>
      </div>
    </div>
  );
}
