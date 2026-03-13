'use client';

import { useSession } from 'next-auth/react';
import { useEffect, useState } from 'react';
import Link from 'next/link';
import { AgentPanel } from '@/components/AgentPanel';
import { toast } from 'sonner';

interface BrokerConnection {
  id: string;
  broker: string;
  label: string | null;
  isActive: boolean;
  createdAt: string;
}

type BrokerFormState = {
  apiKey: string;
  apiSecret: string;
  environment?: string;
  passphrase?: string;
  simulated?: boolean;
  label?: string;
};

export default function SettingsPage() {
  const { data: session, update: updateSession } = useSession();
  const user = session?.user;

  const [connections, setConnections] = useState<BrokerConnection[]>([]);
  const [expandedBroker, setExpandedBroker] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ broker: string; success: boolean; message: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  // Profile editing
  const [editingProfile, setEditingProfile] = useState(false);
  const [profileName, setProfileName] = useState('');
  const [profileEmail, setProfileEmail] = useState('');
  const [savingProfile, setSavingProfile] = useState(false);

  // Password change
  const [showPasswordForm, setShowPasswordForm] = useState(false);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [savingPassword, setSavingPassword] = useState(false);

  // Form state per broker
  const [alpacaForm, setAlpacaForm] = useState<BrokerFormState>({
    apiKey: '', apiSecret: '', environment: 'paper', label: 'Alpaca Paper',
  });
  const [bitgetForm, setBitgetForm] = useState<BrokerFormState>({
    apiKey: '', apiSecret: '', passphrase: '', simulated: false, label: 'Bitget Spot',
  });

  useEffect(() => {
    fetchConnections();
  }, []);

  useEffect(() => {
    if (user) {
      setProfileName(user.name || '');
      setProfileEmail(user.email || '');
    }
  }, [user]);

  const fetchConnections = async () => {
    const res = await fetch('/api/broker');
    if (res.ok) setConnections(await res.json());
  };

  const isConnected = (broker: string) => connections.some((c) => c.broker === broker && c.isActive);

  const testConnection = async (broker: string) => {
    setTesting(true);
    setTestResult(null);
    const form = broker === 'ALPACA' ? alpacaForm : bitgetForm;
    try {
      const res = await fetch('/api/broker/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ broker, ...form }),
      });
      const data = await res.json();
      const success = data.success;
      const message = success
        ? `Connected! ${data.account ? `Equity: $${Number(data.account.equity).toLocaleString()}` : 'Verified'}`
        : data.error || 'Connection failed';
      setTestResult({ broker, success, message });
      if (success) toast.success(message);
      else toast.error(message);
    } catch {
      setTestResult({ broker, success: false, message: 'Request failed' });
      toast.error('Connection test failed');
    }
    setTesting(false);
  };

  const saveConnection = async (broker: string) => {
    setSaving(true);
    const form = broker === 'ALPACA' ? alpacaForm : bitgetForm;
    try {
      const res = await fetch('/api/broker', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ broker, ...form }),
      });
      if (res.ok) {
        await fetchConnections();
        setExpandedBroker(null);
        setTestResult(null);
        toast.success(`${broker} connection saved`);
      } else {
        toast.error('Failed to save connection');
      }
    } catch {
      toast.error('Failed to save connection');
    }
    setSaving(false);
  };

  const deleteConnection = async (id: string) => {
    await fetch(`/api/broker?id=${id}`, { method: 'DELETE' });
    await fetchConnections();
    toast.success('Connection removed');
  };

  const saveProfile = async () => {
    setSavingProfile(true);
    try {
      const res = await fetch('/api/user/profile', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: profileName, email: profileEmail }),
      });
      const data = await res.json();
      if (res.ok) {
        setEditingProfile(false);
        await updateSession();
        if (data.emailChanged) {
          toast.success('Profile updated. Check your new email for verification.');
        } else {
          toast.success('Profile updated');
        }
      } else {
        toast.error(data.error || 'Failed to update profile');
      }
    } catch {
      toast.error('Failed to update profile');
    }
    setSavingProfile(false);
  };

  const changePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast.error('Passwords do not match');
      return;
    }
    if (newPassword.length < 8) {
      toast.error('Password must be at least 8 characters');
      return;
    }
    setSavingPassword(true);
    try {
      const res = await fetch('/api/user/change-password', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ currentPassword, newPassword }),
      });
      const data = await res.json();
      if (res.ok) {
        setShowPasswordForm(false);
        setCurrentPassword('');
        setNewPassword('');
        setConfirmPassword('');
        toast.success('Password changed successfully');
      } else {
        toast.error(data.error || 'Failed to change password');
      }
    } catch {
      toast.error('Failed to change password');
    }
    setSavingPassword(false);
  };

  const inputClass = 'w-full rounded-lg border border-nq-border bg-nq-bg px-3 py-2 text-sm text-nq-text placeholder-nq-muted/50 focus:border-nq-accent focus:outline-none transition';

  return (
    <div className="min-h-screen bg-nq-bg pb-20 lg:pb-0">
      <header className="border-b border-nq-border px-6 py-4">
        <div className="flex items-center gap-3">
          <Link href="/" className="text-nq-muted hover:text-nq-text transition">
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5 3 12m0 0 7.5-7.5M3 12h18" />
            </svg>
          </Link>
          <h1 className="text-xl font-semibold text-nq-text">Settings</h1>
        </div>
      </header>

      <div className="max-w-2xl mx-auto px-6 py-8 space-y-8">
        {/* Profile */}
        <section className="rounded-xl border border-nq-border bg-nq-card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-nq-text">Profile</h2>
            {!editingProfile && (
              <button
                onClick={() => setEditingProfile(true)}
                className="text-xs text-nq-accent hover:underline"
              >
                Edit
              </button>
            )}
          </div>

          {editingProfile ? (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-nq-muted block mb-1">Name</label>
                <input className={inputClass} value={profileName} onChange={(e) => setProfileName(e.target.value)} />
              </div>
              <div>
                <label className="text-xs text-nq-muted block mb-1">Email</label>
                <input className={inputClass} type="email" value={profileEmail} onChange={(e) => setProfileEmail(e.target.value)} />
              </div>
              <div className="flex gap-2">
                <button onClick={saveProfile} disabled={savingProfile}
                  className="px-3 py-2 text-xs rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition disabled:opacity-50">
                  {savingProfile ? 'Saving...' : 'Save'}
                </button>
                <button onClick={() => { setEditingProfile(false); setProfileName(user?.name || ''); setProfileEmail(user?.email || ''); }}
                  className="px-3 py-2 text-xs rounded-lg border border-nq-border text-nq-muted hover:text-nq-text transition">
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-2 gap-4 text-sm">
              <div>
                <span className="text-nq-muted">Name</span>
                <p className="text-nq-text">{user?.name || '—'}</p>
              </div>
              <div>
                <span className="text-nq-muted">Email</span>
                <p className="text-nq-text">{user?.email || '—'}</p>
              </div>
            </div>
          )}
        </section>

        {/* Security */}
        <section className="rounded-xl border border-nq-border bg-nq-card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-nq-text">Security</h2>
            {!showPasswordForm && (
              <button
                onClick={() => setShowPasswordForm(true)}
                className="text-xs text-nq-accent hover:underline"
              >
                Change Password
              </button>
            )}
          </div>

          {showPasswordForm && (
            <div className="space-y-3">
              <div>
                <label className="text-xs text-nq-muted block mb-1">Current Password</label>
                <input className={inputClass} type="password" value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)} placeholder="Enter current password" />
              </div>
              <div>
                <label className="text-xs text-nq-muted block mb-1">New Password</label>
                <input className={inputClass} type="password" value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)} placeholder="Min. 8 characters" />
              </div>
              <div>
                <label className="text-xs text-nq-muted block mb-1">Confirm New Password</label>
                <input className={inputClass} type="password" value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)} placeholder="Repeat new password" />
              </div>
              <div className="flex gap-2">
                <button onClick={changePassword} disabled={savingPassword}
                  className="px-3 py-2 text-xs rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition disabled:opacity-50">
                  {savingPassword ? 'Changing...' : 'Change Password'}
                </button>
                <button onClick={() => { setShowPasswordForm(false); setCurrentPassword(''); setNewPassword(''); setConfirmPassword(''); }}
                  className="px-3 py-2 text-xs rounded-lg border border-nq-border text-nq-muted hover:text-nq-text transition">
                  Cancel
                </button>
              </div>
            </div>
          )}
        </section>

        {/* Plan */}
        <section className="rounded-xl border border-nq-border bg-nq-card p-6 space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-nq-text">Plan</h2>
            <span className={`px-3 py-1 rounded-full text-sm font-medium ${
              user?.plan === 'PRO' ? 'bg-nq-accent/20 text-nq-accent' : 'bg-nq-border text-nq-muted'
            }`}>
              {user?.plan || 'FREE'}
            </span>
          </div>
          {user?.plan !== 'PRO' ? (
            <div className="rounded-lg bg-nq-accent/5 border border-nq-accent/20 p-4">
              <h3 className="text-sm font-semibold text-nq-accent mb-2">Upgrade to Pro</h3>
              <ul className="text-xs text-nq-muted space-y-1">
                <li>All 5 exchanges (CRYPTO, US, LSE, BME, TSE)</li>
                <li>Unlimited AI chat</li>
                <li>Trade execution via connected brokers</li>
                <li>Advanced analytics dashboard</li>
                <li>Trade export (CSV/PDF)</li>
              </ul>
              <button
                onClick={async () => {
                  try {
                    const res = await fetch('/api/billing/create-checkout', { method: 'POST' });
                    const data = await res.json();
                    if (data.url) window.location.href = data.url;
                    else toast.error('Failed to start checkout');
                  } catch { toast.error('Failed to start checkout'); }
                }}
                className="mt-3 px-4 py-2 text-xs font-medium rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition"
              >
                Upgrade to Pro
              </button>
            </div>
          ) : (
            <div className="text-sm text-nq-muted">
              <p>You have full access to all features.</p>
              <button
                onClick={async () => {
                  try {
                    const res = await fetch('/api/billing/portal', { method: 'POST' });
                    const data = await res.json();
                    if (data.url) window.location.href = data.url;
                    else toast.error('Failed to open billing portal');
                  } catch { toast.error('Failed to open billing portal'); }
                }}
                className="mt-2 text-xs text-nq-accent hover:underline"
              >
                Manage Subscription
              </button>
            </div>
          )}
        </section>

        {/* Trading Agent */}
        <AgentPanel />

        {/* Broker Connections */}
        <section className="rounded-xl border border-nq-border bg-nq-card p-6 space-y-4">
          <h2 className="text-lg font-semibold text-nq-text">Broker Connections</h2>
          <p className="text-sm text-nq-muted">
            Connect your broker to execute trades. API keys are encrypted at rest.
          </p>

          {/* Alpaca */}
          <div className="rounded-lg border border-nq-border overflow-hidden">
            <div
              className="flex items-center justify-between p-4 cursor-pointer hover:bg-nq-bg/50 transition"
              onClick={() => setExpandedBroker(expandedBroker === 'ALPACA' ? null : 'ALPACA')}
            >
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded bg-nq-green/10 flex items-center justify-center text-sm font-bold text-nq-green">A</div>
                <div>
                  <p className="text-sm font-medium text-nq-text">Alpaca</p>
                  <p className="text-xs text-nq-muted">US stocks (NYSE/NASDAQ)</p>
                </div>
              </div>
              {isConnected('ALPACA') ? (
                <span className="text-xs bg-nq-green/10 text-nq-green px-2 py-1 rounded">Connected</span>
              ) : (
                <span className="text-xs text-nq-muted">Click to setup</span>
              )}
            </div>

            {expandedBroker === 'ALPACA' && (
              <div className="border-t border-nq-border p-4 space-y-3 bg-nq-bg/30">
                <input className={inputClass} placeholder="API Key" value={alpacaForm.apiKey}
                  onChange={(e) => setAlpacaForm({ ...alpacaForm, apiKey: e.target.value })} />
                <input className={inputClass} type="password" placeholder="API Secret" value={alpacaForm.apiSecret}
                  onChange={(e) => setAlpacaForm({ ...alpacaForm, apiSecret: e.target.value })} />
                <select className={inputClass} value={alpacaForm.environment}
                  onChange={(e) => setAlpacaForm({ ...alpacaForm, environment: e.target.value })}>
                  <option value="paper">Paper Trading</option>
                  <option value="live">Live Trading</option>
                </select>

                {testResult?.broker === 'ALPACA' && (
                  <div className={`rounded-lg p-3 text-xs ${testResult.success ? 'bg-nq-green/10 text-nq-green' : 'bg-nq-red/10 text-nq-red'}`}>
                    {testResult.message}
                  </div>
                )}

                <div className="flex gap-2">
                  <button onClick={() => testConnection('ALPACA')} disabled={testing || !alpacaForm.apiKey}
                    className="px-3 py-2 text-xs rounded-lg border border-nq-border text-nq-text hover:bg-nq-bg transition disabled:opacity-50">
                    {testing ? 'Testing...' : 'Test Connection'}
                  </button>
                  <button onClick={() => saveConnection('ALPACA')} disabled={saving || !alpacaForm.apiKey}
                    className="px-3 py-2 text-xs rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition disabled:opacity-50">
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                  {isConnected('ALPACA') && (
                    <button onClick={() => { const c = connections.find(x => x.broker === 'ALPACA'); if (c) deleteConnection(c.id); }}
                      className="px-3 py-2 text-xs rounded-lg text-nq-red hover:bg-nq-red/10 transition">
                      Disconnect
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Bitget */}
          <div className="rounded-lg border border-nq-border overflow-hidden">
            <div
              className="flex items-center justify-between p-4 cursor-pointer hover:bg-nq-bg/50 transition"
              onClick={() => setExpandedBroker(expandedBroker === 'BITGET' ? null : 'BITGET')}
            >
              <div className="flex items-center gap-3">
                <div className="h-8 w-8 rounded bg-nq-yellow/10 flex items-center justify-center text-sm font-bold text-nq-yellow">B</div>
                <div>
                  <p className="text-sm font-medium text-nq-text">Bitget</p>
                  <p className="text-xs text-nq-muted">Crypto (BTC, ETH, SOL...)</p>
                </div>
              </div>
              {isConnected('BITGET') ? (
                <span className="text-xs bg-nq-green/10 text-nq-green px-2 py-1 rounded">Connected</span>
              ) : (
                <span className="text-xs text-nq-muted">Click to setup</span>
              )}
            </div>

            {expandedBroker === 'BITGET' && (
              <div className="border-t border-nq-border p-4 space-y-3 bg-nq-bg/30">
                <input className={inputClass} placeholder="API Key" value={bitgetForm.apiKey}
                  onChange={(e) => setBitgetForm({ ...bitgetForm, apiKey: e.target.value })} />
                <input className={inputClass} type="password" placeholder="API Secret" value={bitgetForm.apiSecret}
                  onChange={(e) => setBitgetForm({ ...bitgetForm, apiSecret: e.target.value })} />
                <input className={inputClass} type="password" placeholder="Passphrase" value={bitgetForm.passphrase || ''}
                  onChange={(e) => setBitgetForm({ ...bitgetForm, passphrase: e.target.value })} />

                <label className="flex items-center gap-2 cursor-pointer select-none">
                  <input
                    type="checkbox"
                    checked={bitgetForm.simulated || false}
                    onChange={(e) => setBitgetForm({
                      ...bitgetForm,
                      simulated: e.target.checked,
                      label: e.target.checked ? 'Bitget Simulated' : 'Bitget Spot',
                    })}
                    className="h-4 w-4 rounded border-nq-border accent-nq-accent"
                  />
                  <span className="text-xs text-nq-muted">Simulated / Demo Trading</span>
                  {bitgetForm.simulated && (
                    <span className="text-[9px] px-1.5 py-0.5 rounded bg-nq-yellow/15 text-nq-yellow border border-nq-yellow/25">DEMO</span>
                  )}
                </label>

                {testResult?.broker === 'BITGET' && (
                  <div className={`rounded-lg p-3 text-xs ${testResult.success ? 'bg-nq-green/10 text-nq-green' : 'bg-nq-red/10 text-nq-red'}`}>
                    {testResult.message}
                  </div>
                )}

                <div className="flex gap-2">
                  <button onClick={() => testConnection('BITGET')} disabled={testing || !bitgetForm.apiKey}
                    className="px-3 py-2 text-xs rounded-lg border border-nq-border text-nq-text hover:bg-nq-bg transition disabled:opacity-50">
                    {testing ? 'Testing...' : 'Test Connection'}
                  </button>
                  <button onClick={() => saveConnection('BITGET')} disabled={saving || !bitgetForm.apiKey}
                    className="px-3 py-2 text-xs rounded-lg bg-nq-accent text-white hover:bg-nq-accent/90 transition disabled:opacity-50">
                    {saving ? 'Saving...' : 'Save'}
                  </button>
                  {isConnected('BITGET') && (
                    <button onClick={() => { const c = connections.find(x => x.broker === 'BITGET'); if (c) deleteConnection(c.id); }}
                      className="px-3 py-2 text-xs rounded-lg text-nq-red hover:bg-nq-red/10 transition">
                      Disconnect
                    </button>
                  )}
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Footer links */}
        <div className="flex items-center justify-center gap-4 text-xs text-nq-muted pt-4">
          <Link href="/terms" className="hover:text-nq-text transition">Terms of Service</Link>
          <span>·</span>
          <Link href="/privacy" className="hover:text-nq-text transition">Privacy Policy</Link>
        </div>
      </div>
    </div>
  );
}
