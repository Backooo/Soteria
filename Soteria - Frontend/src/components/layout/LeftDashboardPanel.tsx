import React from 'react';
import { FleetKpiCards } from '../fleet/FleetKpiCards';
import { EfficiencySparkline } from '../fleet/EfficiencySparkline';
import { VehicleChassisCard } from '../fleet/VehicleChassisCard';
import { useFleet } from '../../context/FleetContext';

export const LeftDashboardPanel: React.FC = () => {
  const { assets, filterType } = useFleet();

  // Filter assets based on active counter pill or offline filter
  const displayedAssets = assets.filter((asset) => {
    if (filterType === 'train') return asset.type === 'train';
    if (filterType === 'truck') return asset.type === 'truck';
    if (filterType === 'warning') return asset.status !== 'online';
    return true;
  });

  // Pick up to 4 assets to display in the 2x2 schematic grid
  const gridAssets = displayedAssets.slice(0, 4);

  return (
    <aside className="left-dashboard-panel">
      {/* 1. KPI Cards ("Online 5", "Offline 1") */}
      <FleetKpiCards />

      {/* 3. Operational Efficiency Sparkline (78.3%) */}
      <EfficiencySparkline />

      {/* 4. Technical Vehicle Chassis Cards Grid (2x2) */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '6px' }}>
        {gridAssets.map((asset, index) => (
          <VehicleChassisCard 
            key={asset.id} 
            asset={asset}
            timeRangeStart={index % 2 === 0 ? '06AM' : '05AM'}
            timeRangeEnd={index % 2 === 0 ? '11PM' : '09PM'}
          />
        ))}
      </div>
    </aside>
  );
};
