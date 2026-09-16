import React from 'react';
import { AlertTriangle, CheckCircle2 } from 'lucide-react';
import { useFleet } from '../../context/FleetContext';

export const FleetKpiCards: React.FC = () => {
  const { metrics, filterType, setFilterType } = useFleet();

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
      {/* Online KPI Card */}
      <div 
        className={`glass-card ${filterType === 'all' ? '' : ''}`}
        onClick={() => setFilterType('all')}
        style={{ 
          padding: '10px 14px', 
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '4px' }}>
          <CheckCircle2 size={15} color="var(--accent-emerald)" />
          <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
            Online
          </span>
        </div>
        <span style={{ fontSize: '28px', fontWeight: 600, color: '#ffffff', letterSpacing: '-0.02em' }}>
          {metrics.onlineCount}
        </span>
      </div>

      {/* Offline / Alert KPI Card */}
      <div 
        className={`glass-card ${filterType === 'warning' ? 'selected' : ''}`}
        onClick={() => setFilterType(filterType === 'warning' ? 'all' : 'warning')}
        style={{ 
          padding: '10px 14px', 
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: '4px' }}>
          <AlertTriangle size={15} color="var(--accent-rose)" />
          <span style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)' }}>
            Offline
          </span>
        </div>
        <span style={{ fontSize: '28px', fontWeight: 600, color: '#ffffff', letterSpacing: '-0.02em' }}>
          {metrics.offlineCount}
        </span>
      </div>
    </div>
  );
};
