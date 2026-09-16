import React, { useState } from 'react';
import { FleetProvider, useFleet } from './context/FleetContext';
import { TopNavBar } from './components/layout/TopNavBar';
import { InteractiveMap3D } from './components/map/InteractiveMap3D';
import { MapFloatingOverlay } from './components/map/MapFloatingOverlay';
import { LeftDashboardPanel } from './components/layout/LeftDashboardPanel';
import { BottomMetricsPanel } from './components/layout/BottomMetricsPanel';
import { IncidentDrawer } from './components/incidents/IncidentDrawer';
import { AddAssetModal } from './components/modals/AddAssetModal';
import { EditAssetDrawer } from './components/modals/EditAssetDrawer';
import { ConsensusModal } from './components/modals/ConsensusModal';

const DashboardContent: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>('live-map');
  const [isMapOnlyMode, setIsMapOnlyMode] = useState<boolean>(false);
  const [isEditDrawerOpen, setIsEditDrawerOpen] = useState(false);

  const handleTabChange = (tabId: string) => {
    setActiveTab(tabId);
  };

  const toggleMapOnlyMode = () => {
    setIsMapOnlyMode(prev => !prev);
  };

  return (
    <div className="app-container">
      {/* 1. Full-screen 3D Mapbox Viewport in background */}
      <InteractiveMap3D />

      {/* 2. Top Navigation Bar */}
      <TopNavBar 
        activeTab={activeTab} 
        setActiveTab={handleTabChange}
        isMapOnlyMode={isMapOnlyMode}
        toggleMapOnlyMode={toggleMapOnlyMode}
      />

      {/* 3. Floating UI Elements Overlay (Hidden when isMapOnlyMode is true!) */}
      {!isMapOnlyMode && (
        <div className="floating-overlay-container">
          {/* Center Floating Header & Tooltip */}
          <MapFloatingOverlay onOpenEdit={() => setIsEditDrawerOpen(!isEditDrawerOpen)} />

          {/* Left Operational Column (KPIs, Efficiency 78.3%, Vehicle Chassis cards) */}
          <LeftDashboardPanel />

          {/* Right Warnings & Alert Accordion */}
          <IncidentDrawer />

          {/* Bottom Metrics (Schedule Offset ±2.5 min & Live Volume 142,580) */}
          <BottomMetricsPanel />

          {/* Floating Unit Editor Drawer */}
          {isEditDrawerOpen && (
            <EditAssetDrawer onClose={() => setIsEditDrawerOpen(false)} />
          )}
        </div>
      )}



      {/* 4. Interactive Modals */}
      <AddAssetModal />
    </div>
  );
};

export function App() {
  return (
    <FleetProvider>
      <DashboardContent />
    </FleetProvider>
  );
}

export default App;
