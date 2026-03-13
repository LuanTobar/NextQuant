'use client';

import { useState, useEffect, useCallback } from 'react';
import { useSession } from 'next-auth/react';
import clsx from 'clsx';

interface AgentConfigData {
  enabled: boolean;
  broker: string;
  maxPositionSizeUsd: number;
  maxConcurrentPositions: number;
  dailyLossLimitUsd: number;
  maxDrawdownPct: number;
  aggressiveness: number;
  allowedSymbols: string[];
}

const DEFAULT_CONFIG: AgentConfigData = {
  enabled: false,
  broker: 'BITGET',
  maxPositionSizeUsd: 100,
  maxConcurrentPositions: 3,
  dailyLossLimitUsd: 500,
  maxDrawdownPct: 10,
  aggressiveness: 0.5,
  allowedSymbols: [],
};

export function AgentPanel() {
  const { data: session } = useSession();
  const isPro = session?.user?.plan === 'PRO';

  const [config, setConfig] = useState<AgentConfigData>(DEFAULT_CONFIG);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);
  const [commanding, setCommanding] = useState(false);
  const [symbolInput, setSymbolInput] = useState('');

  const fetchConfig = useCallback(async () => {
    try {
      const res = await fetch('/api/agent/config');
      if (res.ok) {
        const data = await res.json();
        setConfig(data);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    if (isPro) fetchConfig();
  }, [isPro, fetchConfig]);

  const saveConfig = async () => {
    setSaving(true);
    setSaved(false);
    try {
      const res = await fetch('/api/agent/config', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      if (res.ok) {
        setSaved(true);
        setTimeout(() => setSaved(false), 2000);
      }
    } catch { /* ignore */ }
    setSaving(false);
  };

  const sendCommand = async (action: string) => {
    setCommanding(true);
    try {
      await fetch('/api/agent/command', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action }),
      });
      // Refresh config to reflect changes
      await fetchConfig();
    } catch { /* ignore */ }
    setCommanding(false);
  };

  const addSymbol = () => {
    const sym = symbolInput.trim().toUpperCase();
    if (sym && !config.allowedSymbols.includes(sym)) {
      setConfig({ ...config, allowedSymbols: [...config.allowedSymbols, sym] });
    }
    setSymbolInput('');
  };

  const removeSymbol = (sym: string) => {
    setConfig({
      ...config,
      allowedSymbols: config.allowedSymbols.filter((s) => s !== sym),
    });
  };

  const aggrLabel =
    config.aggressiveness < 0.33 ? 'Conservative' :
    config.aggressiveness < 0.66 ? 'Moderate' : 'Aggressive';

  if (!isPro) {
    return (
      <section className="rounded-xl border border-nq-border bg-nq-card p-6">
        <h2 className="text-lg font-semibold text-nq-text mb-2">Trading Agent</h2>
        <p className="text-sm text-nq-muted">Upgrade to Pro to use the autonomous trading agent.</p>
      </section>
    );
  }

  const inputClass = 'w-full rounded-lg border border-nq-border bg-nq-bg px-3 py-2 text-sm text-nq-text focus:border-nq-accent focus:outline-none transition';

  return (
    <section className="rounded-xl border border-nq-border bg-nq-card p-6 space-y-5">
      {/* Header + Toggle */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-nq-text">Trading Agent</h2>
          <p className="text-xs text-nq-muted mt-0.5">AI-powered autonomous trading</p>
        </div>
        <div className="flex items-center gap-3">
          {config.enabled && (
            <span className="flex items-center gap-1.5 text-xs">
              <span className="h-2 w-2 rounded-full bg-nq-green animate-pulse" />
              <span className="text-nq-green">Running</span>
            </span>
          )}
          <button
            onClick={() => {
              const newEnabled = !config.enabled;
              setConfig({ ...config, enabled: newEnabled });
              // Auto-save toggle
              fetch('/api/agent/config', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ...config, enabled: newEnabled }),
              });
            }}
            className={clsx(
              'relative w-11 h-6 rounded-full transition',
              config.enabled ? 'bg-nq-green' : 'bg-nq-border'
            )}
          >
            <span
              className={clsx(
                'absolute top-0.5 left-0.5 h-5 w-5 rounded-full bg-white transition-transform',
                config.enabled && 'translate-x-5'
              )}
            />
          </button>
        </div>
      </div>

      {/* Config */}
      <div className="space-y-4">
        {/* Broker */}
        <div>
          <label className="text-xs text-nq-muted block mb-1">Broker</label>
          <select
            className={inputClass}
            value={config.broker}
            onChange={(e) => setConfig({ ...config, broker: e.target.value })}
          >
            <option value="BITGET">Bitget (Crypto)</option>
            <option value="ALPACA">Alpaca (US Stocks)</option>
          </select>
        </div>

        {/* Position Size + Max Positions */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-nq-muted block mb-1">Max Position ($)</label>
            <input
              type="number" className={inputClass}
              value={config.maxPositionSizeUsd}
              onChange={(e) => setConfig({ ...config, maxPositionSizeUsd: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="text-xs text-nq-muted block mb-1">Max Positions</label>
            <input
              type="number" className={inputClass}
              value={config.maxConcurrentPositions}
              onChange={(e) => setConfig({ ...config, maxConcurrentPositions: Number(e.target.value) })}
            />
          </div>
        </div>

        {/* Risk Limits */}
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-nq-muted block mb-1">Daily Loss Limit ($)</label>
            <input
              type="number" className={inputClass}
              value={config.dailyLossLimitUsd}
              onChange={(e) => setConfig({ ...config, dailyLossLimitUsd: Number(e.target.value) })}
            />
          </div>
          <div>
            <label className="text-xs text-nq-muted block mb-1">Max Drawdown (%)</label>
            <input
              type="number" className={inputClass}
              value={config.maxDrawdownPct}
              onChange={(e) => setConfig({ ...config, maxDrawdownPct: Number(e.target.value) })}
            />
          </div>
        </div>

        {/* Aggressiveness */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-xs text-nq-muted">Aggressiveness</label>
            <span className={clsx(
              'text-xs font-medium',
              config.aggressiveness < 0.33 ? 'text-nq-green' :
              config.aggressiveness < 0.66 ? 'text-nq-yellow' : 'text-nq-red'
            )}>
              {aggrLabel} ({(config.aggressiveness * 100).toFixed(0)}%)
            </span>
          </div>
          <input
            type="range" min="0" max="1" step="0.05"
            value={config.aggressiveness}
            onChange={(e) => setConfig({ ...config, aggressiveness: Number(e.target.value) })}
            className="w-full accent-nq-accent"
          />
        </div>

        {/* Allowed Symbols */}
        <div>
          <label className="text-xs text-nq-muted block mb-1">
            Allowed Symbols {config.allowedSymbols.length === 0 && '(all)'}
          </label>
          <div className="flex gap-2 mb-2">
            <input
              className={inputClass}
              placeholder="e.g. BTCUSDT"
              value={symbolInput}
              onChange={(e) => setSymbolInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && addSymbol()}
            />
            <button
              onClick={addSymbol}
              className="px-3 py-2 text-xs rounded-lg border border-nq-border text-nq-text hover:bg-nq-bg transition"
            >
              Add
            </button>
          </div>
          {config.allowedSymbols.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {config.allowedSymbols.map((sym) => (
                <span
                  key={sym}
                  className="inline-flex items-center gap-1 px-2 py-0.5 rounded bg-nq-accent/10 text-nq-accent text-xs"
                >
                  {sym}
                  <button onClick={() => removeSymbol(sym)} className="hover:text-nq-red">
                    &times;
                  </button>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2 pt-2 border-t border-nq-border">
        <button
          onClick={saveConfig}
          disabled={saving}
          className="px-4 py-2 text-sm rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition disabled:opacity-50"
        >
          {saving ? 'Saving...' : saved ? 'Saved!' : 'Save Config'}
        </button>

        {config.enabled && (
          <>
            <button
              onClick={() => sendCommand('pause')}
              disabled={commanding}
              className="px-3 py-2 text-xs rounded-lg border border-nq-border text-nq-yellow hover:bg-nq-yellow/10 transition disabled:opacity-50"
            >
              Pause
            </button>
            <button
              onClick={() => {
                if (confirm('Close ALL open positions? This cannot be undone.')) {
                  sendCommand('close_all');
                }
              }}
              disabled={commanding}
              className="px-3 py-2 text-xs rounded-lg border border-nq-red/30 text-nq-red hover:bg-nq-red/10 transition disabled:opacity-50"
            >
              Close All
            </button>
          </>
        )}

        {!config.enabled && (
          <button
            onClick={() => sendCommand('resume')}
            disabled={commanding}
            className="px-3 py-2 text-xs rounded-lg border border-nq-green/30 text-nq-green hover:bg-nq-green/10 transition disabled:opacity-50"
          >
            Resume
          </button>
        )}
      </div>
    </section>
  );
}
