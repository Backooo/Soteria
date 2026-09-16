import React from 'react';
import { ArrowUpRight } from 'lucide-react';
import { useFleet } from '../../context/FleetContext';

export const LiveVolumeChart: React.FC = () => {
  const { assets } = useFleet();

  const totalWagons = assets.reduce((sum, a) => sum + a.compartments.length, 0);
  const affectedWagons = assets.reduce(
    (sum, a) => sum + a.compartments.filter(c => c.status !== 'nominal').length,
    0
  );

  const wagonBins = assets.map((asset) => {
    const affected = asset.compartments.filter(c => c.status !== 'nominal').length;
    const maxWagons = Math.max(...assets.map(a => a.compartments.length), 1);
    return {
      label: asset.name.replace('Freight train ', ''),
      wagonCount: asset.compartments.length,
      affected,
      highlight: affected > 0,
      heightPct: Math.round((asset.compartments.length / maxWagons) * 100),
    };
  });

  return (
    <div className="glass-card" style={{ padding: '10px 14px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
          Affected wagons
        </span>
        <span className="card-header-icon">
          <ArrowUpRight size={15} />
        </span>
      </div>

      {/* Main Stat */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '6px' }}>
        <span style={{ fontSize: '24px', fontWeight: 600, color: '#ffffff', letterSpacing: '-0.02em' }}>
          {affectedWagons} / {totalWagons}
        </span>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Wagons across 3 active incidents
        </span>
      </div>

      {/* Wagon Count Chart Visual */}
      <div style={{ position: 'relative', height: '64px', width: '100%', display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: '10px' }}>
        {wagonBins.map((bin, idx) => (
          <div
            key={idx}
            style={{
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '4px',
              flex: 1,
              height: '100%',
              justifyContent: 'flex-end'
            }}
          >
            {/* Wagon count / affected badge above bar */}
            <div style={{ fontSize: '10px', color: bin.highlight ? 'var(--accent-amber)' : 'var(--text-dim)', fontFamily: 'var(--font-mono)', textAlign: 'center' }}>
              <span>{bin.wagonCount}</span>
              <span style={{ display: 'block', fontSize: '8px', color: bin.highlight ? 'var(--text-amber)' : 'var(--text-dim)' }}>
                {bin.affected > 0 ? `${bin.affected} betroffen` : 'ok'}
              </span>
            </div>

            {/* Bar */}
            <div
              style={{
                width: '18px',
                height: `${bin.heightPct}%`,
                background: bin.highlight
                  ? 'linear-gradient(180deg, rgba(245, 158, 11, 0.6) 0%, rgba(245, 158, 11, 0.1) 100%)'
                  : 'linear-gradient(180deg, rgba(255, 255, 255, 0.15) 0%, rgba(255, 255, 255, 0.02) 100%)',
                border: bin.highlight ? '1px solid var(--accent-amber)' : '1px solid rgba(255, 255, 255, 0.12)',
                borderRadius: '3px 3px 0 0',
                transition: 'all 0.2s ease',
              }}
            />

            {/* Train label below bar */}
            <span style={{ fontSize: '9px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
              {bin.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
};
