import type { Metadata } from 'next';
import './globals.css';
import { Providers } from './providers';
import { MobileNav } from '@/components/MobileNav';

export const metadata: Metadata = {
  title: 'NexQuant - AI Investment Platform',
  description: 'Zero-friction AI-powered investment platform',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-nq-bg text-nq-text antialiased">
        <Providers>
          <div className="pb-16 lg:pb-0">
            {children}
          </div>
          <MobileNav />
        </Providers>
      </body>
    </html>
  );
}
