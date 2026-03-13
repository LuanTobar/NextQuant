'use client';

import { motion } from 'framer-motion';

export function NQCard({
  children,
  className = '',
  hover = false,
  onClick,
}: {
  children: React.ReactNode;
  className?: string;
  /** Enable subtle lift-on-hover animation */
  hover?: boolean;
  onClick?: () => void;
}) {
  if (hover || onClick) {
    return (
      <motion.div
        whileHover={{ scale: 1.015, y: -2 }}
        transition={{ type: 'spring', stiffness: 380, damping: 28 }}
        onClick={onClick}
        className={`bg-nq-card border border-nq-border rounded-xl ${
          onClick ? 'cursor-pointer' : ''
        } ${className}`}
      >
        {children}
      </motion.div>
    );
  }

  return (
    <div className={`bg-nq-card border border-nq-border rounded-xl ${className}`}>
      {children}
    </div>
  );
}
