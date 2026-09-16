import React from 'react';
import { useFleet } from '../../context/FleetContext';

export const FleetCounterPills: React.FC = () => {
  const { metrics, filterType, setFilterType } = useFleet();

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflowX: 'auto', paddingBottom: '2px' }}>
      <button
        className={`glass-pill ${filterType === 'all' ? 'active' : ''}`}
        onClick={() => setFilterType('all')}
        style={{ flex: 1, justifyContent: 'center' }}
      >
        24 Bus
      </button>

      <button
        className="glass-pill"
        onClick={() => setFilterType('truck')}
        style={{ flex: 1, justifyContent: 'center' }}
      >
        100 Taxi
      </button>

      <button
        className={`glass-pill ${filterType === 'train' ? 'active' : ''}`}
        onClick={() => setFilterType('train')}
        style={{ flex: 1, justifyContent: 'center' }}
      >
        12 Trains
      </button>

      <button
        className="glass-pill"
        style={{ flex: 1, justifyContent: 'center' }}
      >
        13 Trams
      </button>
    </div>
  );
};
