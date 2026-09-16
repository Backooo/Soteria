import React from 'react';
import { ArrowUpRight, Wifi, Radio, MapPin } from 'lucide-react';
import { useFleet } from '../../context/FleetContext';
import { FleetAsset } from '../../types/fleet';

interface VehicleChassisCardProps {
  asset: FleetAsset;
  timeRangeStart?: string;
  timeRangeEnd?: string;
}

export const VehicleChassisCard: React.FC<VehicleChassisCardProps> = ({ 
  asset, 
  timeRangeStart = '06AM', 
  timeRangeEnd = '11PM' 
}) => {
  const { selectedAsset, focusOnAsset, setHoveredAsset } = useFleet();
  const isSelected = selectedAsset?.id === asset.id;
  const isWarning = asset.status === 'warning';
  const isOffline = asset.status === 'offline';

  return (
    <div 
      className={`glass-card ${isSelected ? 'selected' : ''}`}
      onClick={() => focusOnAsset(asset)}
      onMouseEnter={() => setHoveredAsset(asset)}
      onMouseLeave={() => setHoveredAsset(null)}
      style={{ 
        padding: '10px 12px', 
        cursor: 'pointer',
        display: 'flex',
        flexDirection: 'column',
        gap: '6px'
      }}
    >
      {/* Header with Name, Timestamp and Arrow */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between' }}>
        <div>
          <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#ffffff', letterSpacing: '-0.01em' }}>
            {asset.name.split(' ')[0]} {asset.name.split(' ')[1] || ''}
          </h4>
          <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
            {asset.updatedAt}
          </span>
        </div>
        <span className="card-header-icon">
          <ArrowUpRight size={14} />
        </span>
      </div>

      {/* Technical Wireframe Chassis Blueprint */}
      <div 
        style={{
          height: '68px',
          background: 'radial-gradient(ellipse at center, rgba(38, 38, 44, 0.45) 0%, rgba(14, 14, 16, 0.7) 100%)',
          borderRadius: '8px',
          border: '1px solid rgba(255, 255, 255, 0.06)',
          position: 'relative',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden'
        }}
      >
        {/* Subtle grid background */}
        <div 
          style={{
            position: 'absolute',
            inset: 0,
            backgroundImage: 'radial-gradient(rgba(255,255,255,0.08) 1px, transparent 0)',
            backgroundSize: '12px 12px',
            opacity: 0.5
          }} 
        />

        {/* Top-down vehicle wireframe schematic matching reference */}
        <svg width="180" height="48" viewBox="0 0 180 48" fill="none" style={{ position: 'relative', zIndex: 2 }}>
          {/* Outer Vehicle Shell */}
          <rect 
            x="12" 
            y="8" 
            width="156" 
            height="32" 
            rx="6" 
            stroke="rgba(255, 255, 255, 0.35)" 
            strokeWidth="1.2" 
            fill="rgba(20, 20, 24, 0.4)" 
          />
          
          {/* Front Cab */}
          <path d="M 12 14 L 28 14 L 28 34 L 12 34" stroke="rgba(255, 255, 255, 0.25)" strokeWidth="1" />
          
          {/* Wheels / Bogies */}
          <rect x="22" y="4" width="16" height="4" rx="2" fill="rgba(255, 255, 255, 0.4)" />
          <rect x="22" y="40" width="16" height="4" rx="2" fill="rgba(255, 255, 255, 0.4)" />
          <rect x="138" y="4" width="22" height="4" rx="2" fill="rgba(255, 255, 255, 0.4)" />
          <rect x="138" y="40" width="22" height="4" rx="2" fill="rgba(255, 255, 255, 0.4)" />

          {/* Internal Sensor Bays (e.g. L 45623 or R 31564) */}
          <rect 
            x="42" 
            y="13" 
            width="50" 
            height="22" 
            rx="3" 
            stroke={isOffline ? 'var(--accent-rose)' : isWarning ? 'var(--accent-amber)' : 'rgba(255, 255, 255, 0.45)'}
            strokeWidth="1"
            strokeDasharray="2,2"
            fill={isOffline ? 'rgba(239, 68, 68, 0.1)' : isWarning ? 'rgba(245, 158, 11, 0.1)' : 'rgba(255, 255, 255, 0.05)'}
          />
          <text
            x="67"
            y="27"
            fontSize="8"
            fill={isOffline ? 'var(--accent-rose)' : isWarning ? 'var(--text-amber)' : '#ffffff'}
            fontFamily="var(--font-mono)" 
            textAnchor="middle"
            fontWeight="600"
          >
            {asset.compartments[0]?.name.replace('Bay ', '') || 'L 45623'}
          </text>

          {/* Secondary Sensor Compartment */}
          <rect 
            x="100" 
            y="13" 
            width="50" 
            height="22" 
            rx="3" 
            stroke="rgba(255, 255, 255, 0.2)" 
            strokeWidth="1" 
            fill="rgba(255, 255, 255, 0.04)" 
          />
          <text 
            x="125" 
            y="27" 
            fontSize="8" 
            fill="rgba(255, 255, 255, 0.5)" 
            fontFamily="var(--font-mono)" 
            textAnchor="middle"
          >
            {asset.compartments[1]?.name.replace('Bay ', '') || 'R 31564'}
          </text>
        </svg>
      </div>

      {/* Status Bar: Online / Warning + Telemetry Icons */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span
            className={`status-indicator ${isOffline ? 'rose' : isWarning ? 'amber' : 'emerald'}`}
            style={{ width: '6px', height: '6px' }}
          />
          <span style={{ color: isOffline ? 'var(--accent-rose)' : isWarning ? 'var(--text-amber)' : 'var(--text-emerald)', fontWeight: 500 }}>
            {isOffline ? 'Kritisch' : isWarning ? 'Delay Alert' : 'Online'}
          </span>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-muted)' }}>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '10px' }}>
            <Radio size={11} color="var(--text-secondary)" />
            GPS
          </span>
          <span style={{ display: 'flex', alignItems: 'center', gap: '3px', fontSize: '10px' }}>
            <Wifi size={11} color="var(--accent-emerald)" />
            LTE
          </span>
        </div>
      </div>

      {/* Mini Radar / Vector Map Thumbnail */}
      <div 
        style={{
          height: '62px',
          background: '#0c0c0e',
          borderRadius: '6px',
          position: 'relative',
          overflow: 'hidden',
          border: '1px solid rgba(255, 255, 255, 0.06)'
        }}
      >
        {/* Dark road/rail grid lines */}
        <svg width="100%" height="100%" style={{ position: 'absolute', inset: 0, opacity: 0.35 }}>
          <line x1="10" y1="20" x2="180" y2="55" stroke="#ffffff" strokeWidth="1" />
          <line x1="30" y1="60" x2="160" y2="10" stroke="#71717a" strokeWidth="1.5" strokeDasharray="3,3" />
          <circle cx="95" cy="35" r="28" fill="none" stroke="rgba(255,255,255,0.1)" strokeDasharray="2,2" />
        </svg>

        {/* Pinpoint Dot with ripple */}
        <div 
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}
        >
          <div 
            style={{ 
              width: '8px', 
              height: '8px', 
              borderRadius: '50%', 
              background: isWarning ? 'var(--accent-amber)' : '#ffffff',
              boxShadow: `0 0 8px ${isWarning ? 'var(--accent-amber)' : 'rgba(255, 255, 255, 0.6)'}`
            }} 
          />
        </div>
      </div>

      {/* Time Slider */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '2px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>
          <span>{timeRangeStart}</span>
          <span>{timeRangeEnd}</span>
        </div>
        <div style={{ width: '100%', height: '3px', background: 'rgba(255, 255, 255, 0.08)', borderRadius: '99px', position: 'relative' }}>
          <div 
            style={{ 
              position: 'absolute', 
              left: '42%', 
              top: '-3px', 
              width: '9px', 
              height: '9px', 
              borderRadius: '50%', 
              background: '#ffffff',
              boxShadow: '0 0 6px rgba(255,255,255,0.8)'
            }} 
          />
        </div>
      </div>
    </div>
  );
};
