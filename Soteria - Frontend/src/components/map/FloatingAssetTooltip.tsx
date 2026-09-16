import React from 'react';
import { ArrowUpRight, Thermometer, Navigation } from 'lucide-react';
import { useFleet } from '../../context/FleetContext';

export const FloatingAssetTooltip: React.FC<{ onOpenEdit?: () => void }> = ({ onOpenEdit }) => {
  const { hoveredAsset, setHoveredAsset } = useFleet();

  // ONLY render when hovering over an asset!
  if (!hoveredAsset) return null;

  return (
    <div 
      className="glass-floating-tooltip"
      onMouseEnter={() => setHoveredAsset(hoveredAsset)}
      onMouseLeave={() => setHoveredAsset(null)}
      style={{
        position: 'absolute',
        top: '46%',
        left: '51%',
        transform: 'translate(-50%, -50%)',
        pointerEvents: 'auto',
        background: 'rgba(14, 14, 16, 0.75)',
        backdropFilter: 'blur(32px)',
        WebkitBackdropFilter: 'blur(32px)',
        border: '1px solid rgba(255, 255, 255, 0.2)',
        boxShadow: '0 24px 48px rgba(0, 0, 0, 0.8), 0 0 0 1px rgba(255, 255, 255, 0.1) inset',
        animation: 'fadeIn 0.18s ease',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontSize: '13px', color: 'var(--text-secondary)', fontWeight: 500 }}>
          {hoveredAsset.name}
        </span>
        <span 
          className="card-header-icon" 
          onClick={onOpenEdit} 
          title="Einheit konfigurieren / bearbeiten" 
          style={{ cursor: 'pointer' }}
        >
          <ArrowUpRight size={15} />
        </span>
      </div>

      {/* Next destination */}
      <div style={{ fontSize: '11px', color: 'var(--text-muted)', marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '4px' }}>
        <Navigation size={11} color="var(--text-secondary)" />
        <span>Next: {hoveredAsset.nextStation}</span>
      </div>

      {/* Main Stat Percentage */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '8px', marginBottom: '8px' }}>
        <span style={{ fontSize: '38px', fontWeight: 600, letterSpacing: '-0.03em', color: '#ffffff' }}>
          {hoveredAsset.loadPct}%
        </span>
        {hoveredAsset.currentTempC !== undefined && (
          <span 
            style={{ 
              fontSize: '12px', 
              fontFamily: 'var(--font-mono)',
              color: hoveredAsset.currentTempC > (hoveredAsset.targetTempC || -18) + 2 ? 'var(--accent-rose)' : 'var(--accent-emerald)',
              fontWeight: 500,
              display: 'flex',
              alignItems: 'center',
              gap: '2px'
            }}
          >
            <Thermometer size={12} />
            {hoveredAsset.currentTempC > 0 ? `+${hoveredAsset.currentTempC}` : hoveredAsset.currentTempC}°C
          </span>
        )}
      </div>

      {/* Progress Line */}
      <div style={{ width: '100%', height: '3px', background: 'rgba(255,255,255,0.1)', borderRadius: '999px', overflow: 'hidden', marginBottom: '10px' }}>
        <div 
          style={{ 
            width: `${hoveredAsset.loadPct}%`, 
            height: '100%', 
            background: hoveredAsset.status === 'warning' ? 'var(--accent-amber)' : 'linear-gradient(90deg, #ffffff, #a1a1aa)',
            borderRadius: '999px',
            transition: 'width 0.3s ease'
          }} 
        />
      </div>

      {/* Quick metadata & Edit trigger button */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)' }}>
        <span>Speed: {hoveredAsset.speedKmh} km/h</span>
        <button 
          onClick={onOpenEdit}
          style={{ 
            background: 'rgba(255,255,255,0.08)', 
            border: '1px solid rgba(255,255,255,0.12)', 
            borderRadius: '4px', 
            color: 'var(--text-secondary)',
            padding: '2px 8px',
            fontSize: '10px',
            cursor: 'pointer'
          }}
        >
          Bearbeiten ↗
        </button>
      </div>
    </div>
  );
};
