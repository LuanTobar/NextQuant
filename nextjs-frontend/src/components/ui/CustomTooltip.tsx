'use client';

interface TooltipPayload {
  name: string;
  value: number;
  color?: string;
}

export function CustomTooltip({
  active,
  payload,
  label,
  formatter,
}: {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: string;
  formatter?: (value: number, name: string) => [string, string];
}) {
  if (!active || !payload || payload.length === 0) return null;

  return (
    <div className="bg-nq-card border border-nq-border rounded-lg px-3 py-2.5 shadow-xl text-xs min-w-[120px]">
      {label && <p className="text-nq-muted text-[10px] mb-2 font-medium">{label}</p>}
      {payload.map((p, i) => {
        const [fVal, fName] = formatter ? formatter(p.value, p.name) : [String(p.value), p.name];
        return (
          <div key={i} className="flex items-center gap-2">
            {p.color && (
              <div className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: p.color }} />
            )}
            <span className="text-nq-muted">{fName}:</span>
            <span className="text-nq-text font-semibold ml-auto pl-2">{fVal}</span>
          </div>
        );
      })}
    </div>
  );
}

/** Pre-made formatter for money values */
export function moneyFormatter(value: number, name: string): [string, string] {
  const abs = Math.abs(value);
  const formatted =
    abs >= 1000 ? `$${(value / 1000).toFixed(1)}k` : `$${value.toFixed(2)}`;
  return [formatted, name];
}

/** Pre-made formatter for percentage values */
export function pctFormatter(value: number, name: string): [string, string] {
  return [`${value >= 0 ? '+' : ''}${value.toFixed(2)}%`, name];
}
