'use client';

import { useSession, signOut } from 'next-auth/react';
import Link from 'next/link';
import { useState } from 'react';

export function Header() {
  const { data: session } = useSession();
  const user = session?.user;
  const plan = user?.plan || 'FREE';
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <header className="border-b border-nq-border bg-nq-bg/80 backdrop-blur-sm sticky top-0 z-40 px-4 sm:px-6 py-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          {/* Logo mark */}
          <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-nq-accent to-nq-accent/60 flex items-center justify-center font-bold text-white text-sm shadow-lg shadow-nq-accent/20">
            NQ
          </div>
          <div className="hidden sm:flex flex-col leading-none">
            <span className="text-sm font-bold tracking-tight">NexQuant</span>
            <span className="text-[9px] text-nq-muted uppercase tracking-widest">AI Trading</span>
          </div>
        </div>

        {/* Desktop nav */}
        <div className="hidden lg:flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1.5 text-xs font-medium text-nq-green bg-nq-green/10 px-2.5 py-1 rounded-full border border-nq-green/20">
            <span className="relative flex h-1.5 w-1.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-nq-green opacity-75" />
              <span className="relative inline-flex rounded-full h-1.5 w-1.5 bg-nq-green" />
            </span>
            Live
          </span>

          {user && (
            <>
              {plan === 'PRO' && (
                <Link href="/analytics" className="text-nq-muted hover:text-nq-text transition" title="Analytics">
                  <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 0 1 3 19.875v-6.75ZM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V8.625ZM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 0 1-1.125-1.125V4.125Z" />
                  </svg>
                </Link>
              )}

              <span
                className={`px-2 py-0.5 rounded text-xs font-medium ${
                  plan === 'PRO'
                    ? 'bg-nq-accent/20 text-nq-accent'
                    : 'bg-nq-card text-nq-muted'
                }`}
              >
                {plan}
              </span>

              <Link href="/settings" className="text-nq-muted hover:text-nq-text transition" title="Settings">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.594 3.94c.09-.542.56-.94 1.11-.94h2.593c.55 0 1.02.398 1.11.94l.213 1.281c.063.374.313.686.645.87.074.04.147.083.22.127.325.196.72.257 1.075.124l1.217-.456a1.125 1.125 0 0 1 1.37.49l1.296 2.247a1.125 1.125 0 0 1-.26 1.431l-1.003.827c-.293.241-.438.613-.43.992a7.723 7.723 0 0 1 0 .255c-.008.378.137.75.43.991l1.004.827c.424.35.534.955.26 1.43l-1.298 2.247a1.125 1.125 0 0 1-1.369.491l-1.217-.456c-.355-.133-.75-.072-1.076.124a6.47 6.47 0 0 1-.22.128c-.331.183-.581.495-.644.869l-.213 1.281c-.09.543-.56.94-1.11.94h-2.594c-.55 0-1.019-.398-1.11-.94l-.213-1.281c-.062-.374-.312-.686-.644-.87a6.52 6.52 0 0 1-.22-.127c-.325-.196-.72-.257-1.076-.124l-1.217.456a1.125 1.125 0 0 1-1.369-.49l-1.297-2.247a1.125 1.125 0 0 1 .26-1.431l1.004-.827c.292-.24.437-.613.43-.991a6.932 6.932 0 0 1 0-.255c.007-.38-.138-.751-.43-.992l-1.004-.827a1.125 1.125 0 0 1-.26-1.43l1.297-2.247a1.125 1.125 0 0 1 1.37-.491l1.216.456c.356.133.751.072 1.076-.124.072-.044.146-.086.22-.128.332-.183.582-.495.644-.869l.214-1.28Z" />
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 12a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                </svg>
              </Link>

              <div className="flex items-center gap-2">
                {user.image ? (
                  <img src={user.image} alt={user.name || ''} className="h-7 w-7 rounded-full" />
                ) : (
                  <div className="h-7 w-7 rounded-full bg-nq-accent/20 flex items-center justify-center text-xs font-medium text-nq-accent">
                    {(user.name || user.email)?.[0]?.toUpperCase()}
                  </div>
                )}
                <span className="text-nq-text hidden xl:inline">{user.name || user.email}</span>
              </div>

              <button
                onClick={() => signOut({ callbackUrl: '/auth/login' })}
                className="text-nq-muted hover:text-nq-red transition text-xs"
              >
                Sign out
              </button>
            </>
          )}
        </div>

        {/* Mobile hamburger */}
        <button
          className="lg:hidden text-nq-muted hover:text-nq-text transition"
          onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
        >
          {mobileMenuOpen ? (
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18 18 6M6 6l12 12" />
            </svg>
          ) : (
            <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5" />
            </svg>
          )}
        </button>
      </div>

      {/* Mobile dropdown */}
      {mobileMenuOpen && (
        <div className="lg:hidden mt-4 pt-4 border-t border-nq-border space-y-3">
          {user && (
            <>
              <div className="flex items-center gap-2 text-sm">
                {user.image ? (
                  <img src={user.image} alt={user.name || ''} className="h-7 w-7 rounded-full" />
                ) : (
                  <div className="h-7 w-7 rounded-full bg-nq-accent/20 flex items-center justify-center text-xs font-medium text-nq-accent">
                    {(user.name || user.email)?.[0]?.toUpperCase()}
                  </div>
                )}
                <span className="text-nq-text">{user.name || user.email}</span>
                <span className={`ml-auto px-2 py-0.5 rounded text-xs font-medium ${
                  plan === 'PRO' ? 'bg-nq-accent/20 text-nq-accent' : 'bg-nq-card text-nq-muted'
                }`}>
                  {plan}
                </span>
              </div>

              <div className="space-y-1">
                {plan === 'PRO' && (
                  <Link href="/analytics" className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-nq-muted hover:text-nq-text hover:bg-nq-bg transition"
                    onClick={() => setMobileMenuOpen(false)}>
                    Analytics
                  </Link>
                )}
                <Link href="/settings" className="flex items-center gap-2 px-3 py-2 rounded-lg text-sm text-nq-muted hover:text-nq-text hover:bg-nq-bg transition"
                  onClick={() => setMobileMenuOpen(false)}>
                  Settings
                </Link>
                <button
                  onClick={() => signOut({ callbackUrl: '/auth/login' })}
                  className="w-full text-left px-3 py-2 rounded-lg text-sm text-nq-red hover:bg-nq-red/10 transition"
                >
                  Sign out
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </header>
  );
}
