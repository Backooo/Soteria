import React, { createContext, useContext, useState, useEffect } from 'react';
import { FleetAsset, TransitRoute, IncidentAlert, SoteriaConsensusItem, FleetMetrics, AssetType } from '../types/fleet';
import { MOCK_ASSETS, MOCK_ROUTES, MOCK_INCIDENTS, MOCK_SOTERIA_CONSENSUS, MOCK_METRICS, SOTERIA_BY_INCIDENT } from '../data/mockFleetData';

interface FleetContextType {
  assets: FleetAsset[];
  routes: TransitRoute[];
  incidents: IncidentAlert[];
  soteriaConsensus: SoteriaConsensusItem[];
  activeIncident: IncidentAlert | null;
  metrics: FleetMetrics;
  selectedAsset: FleetAsset | null;
  hoveredAsset: FleetAsset | null;
  selectedIncident: IncidentAlert | null;
  isAddModalOpen: boolean;
  isNotificationSidebarOpen: boolean;
  addAssetDraftType: AssetType;
  filterType: 'all' | 'train' | 'truck' | 'warning';
  activeMapStyle: 'satellite-dark' | 'terrain-3d' | 'dark-matter';
  is3DMode: boolean;
  isSimulating: boolean;
  simulationSpeed: number;
  focusedCoordinates: [number, number] | null;
  
  // Actions
  selectAsset: (asset: FleetAsset | null) => void;
  setHoveredAsset: (asset: FleetAsset | null) => void;
  selectIncident: (incident: IncidentAlert | null) => void;
  toggleNotificationSidebar: () => void;
  closeNotificationSidebar: () => void;
  openAddModal: (type?: AssetType) => void;
  closeAddModal: () => void;
  addAsset: (newAsset: Omit<FleetAsset, 'id' | 'updatedAt'>) => void;
  updateAsset: (id: string, updates: Partial<FleetAsset>) => void;
  deleteAsset: (id: string) => void;
  setFilterType: (filter: 'all' | 'train' | 'truck' | 'warning') => void;
  setActiveMapStyle: (style: 'satellite-dark' | 'terrain-3d' | 'dark-matter') => void;
  toggle3DMode: () => void;
  toggleSimulation: () => void;
  setSimulationSpeed: (speed: number) => void;
  focusOnAsset: (asset: FleetAsset) => void;
}

const FleetContext = createContext<FleetContextType | undefined>(undefined);

export const FleetProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [assets, setAssets] = useState<FleetAsset[]>(MOCK_ASSETS);
  const [routes] = useState<TransitRoute[]>(MOCK_ROUTES);
  const [incidents, setIncidents] = useState<IncidentAlert[]>(MOCK_INCIDENTS);
  const [selectedAsset, setSelectedAsset] = useState<FleetAsset | null>(null);
  const [hoveredAsset, setHoveredAsset] = useState<FleetAsset | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<IncidentAlert | null>(null);

  // Operator switches incidents by selecting a train; otherwise the newest incident is shown
  const activeIncident =
    incidents.find(i => selectedAsset && i.assetId === selectedAsset.id) ?? selectedIncident ?? incidents[0] ?? null;
  const soteriaConsensus: SoteriaConsensusItem[] =
    (activeIncident && SOTERIA_BY_INCIDENT[activeIncident.id]?.consensus) || MOCK_SOTERIA_CONSENSUS;

  // Tell an open dev console (console.html) which incident the operator is looking at
  useEffect(() => {
    if (!activeIncident || typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('soteria-console');
    channel.postMessage({ incidentId: activeIncident.id });
    channel.close();
  }, [activeIncident?.id]);
  
  const [isAddModalOpen, setIsAddModalOpen] = useState<boolean>(false);
  const [isNotificationSidebarOpen, setIsNotificationSidebarOpen] = useState<boolean>(false);
  const [addAssetDraftType, setAddAssetDraftType] = useState<AssetType>('train');
  const [filterType, setFilterType] = useState<'all' | 'train' | 'truck' | 'warning'>('all');
  const [activeMapStyle, setActiveMapStyle] = useState<'satellite-dark' | 'terrain-3d' | 'dark-matter'>('satellite-dark');
  const [is3DMode, setIs3DMode] = useState<boolean>(true);
  const [isSimulating, setIsSimulating] = useState<boolean>(true);
  const [simulationSpeed, setSimulationSpeed] = useState<number>(1);
  const [focusedCoordinates, setFocusedCoordinates] = useState<[number, number] | null>(null);

  const toggleNotificationSidebar = () => {
    setIsNotificationSidebarOpen(prev => !prev);
  };

  const closeNotificationSidebar = () => {
    setIsNotificationSidebarOpen(false);
  };

  // Dynamic metrics calculation (derived live from the real asset & incident data)
  const onlineCount = assets.filter(a => a.status === 'online').length;
  const offlineCount = assets.filter(a => a.status !== 'online').length;
  const trainsCount = assets.filter(a => a.type === 'train').length;
  const trucksCount = assets.filter(a => a.type === 'truck').length;
  const wagonsInTransit = assets.reduce((sum, a) => sum + a.compartments.length, 0);

  const metrics: FleetMetrics = {
    ...MOCK_METRICS,
    totalVehicles: assets.length,
    trainsCount,
    trucksCount,
    onlineCount,
    offlineCount,
    wagonsInTransit,
    activeIncidentsCount: incidents.length,
  };

  // Add Asset Handler
  const addAsset = (newAssetData: Omit<FleetAsset, 'id' | 'updatedAt'>) => {
    const id = `asset-${Date.now().toString().slice(-4)}`;
    const newAsset: FleetAsset = {
      ...newAssetData,
      id,
      updatedAt: new Date().toLocaleDateString('de-DE') + ', ' + new Date().toLocaleTimeString('de-DE'),
    };
    setAssets(prev => [newAsset, ...prev]);
    setSelectedAsset(newAsset);
    setFocusedCoordinates(newAsset.coordinates);
    setIsAddModalOpen(false);
  };

  // Update Asset Handler
  const updateAsset = (id: string, updates: Partial<FleetAsset>) => {
    setAssets(prev => prev.map(item => {
      if (item.id === id) {
        const updated = {
          ...item,
          ...updates,
          updatedAt: new Date().toLocaleDateString('de-DE') + ', ' + new Date().toLocaleTimeString('de-DE'),
        };
        if (selectedAsset?.id === id) {
          setSelectedAsset(updated);
        }
        return updated;
      }
      return item;
    }));
  };

  // Delete Asset Handler
  const deleteAsset = (id: string) => {
    setAssets(prev => prev.filter(item => item.id !== id));
    if (selectedAsset?.id === id) {
      setSelectedAsset(null);
    }
  };

  // Focus on asset and zoom map
  const focusOnAsset = (asset: FleetAsset) => {
    setSelectedAsset(asset);
    setFocusedCoordinates(asset.coordinates);
  };

  const openAddModal = (type: AssetType = 'train') => {
    setAddAssetDraftType(type);
    setIsAddModalOpen(true);
  };

  const closeAddModal = () => {
    setIsAddModalOpen(false);
  };

  const toggle3DMode = () => {
    setIs3DMode(prev => !prev);
  };

  const toggleSimulation = () => {
    setIsSimulating(prev => !prev);
  };

  // Live simulation tick: subtly animate moving assets along their routes!
  useEffect(() => {
    if (!isSimulating) return;

    const interval = setInterval(() => {
      setAssets(prevAssets =>
        prevAssets.map(asset => {
          if (asset.speedKmh === 0 || asset.type === 'depot') return asset;

          // Find associated route
          const route = routes.find(r => r.id === asset.routeId) || routes[0];
          if (!route || route.coordinates.length < 2) return asset;

          // Subtle coordinate interpolation step
          const speedFactor = 0.00015 * simulationSpeed;
          const headingRad = (asset.heading * Math.PI) / 180;
          const nextLng = asset.coordinates[0] + Math.sin(headingRad) * speedFactor;
          const nextLat = asset.coordinates[1] + Math.cos(headingRad) * speedFactor;

          // Wrap or steer back if too far from corridor
          const [centerLng, centerLat] = route.coordinates[0];
          const dist = Math.hypot(nextLng - centerLng, nextLat - centerLat);
          const newHeading = dist > 0.12 ? (asset.heading + 180) % 360 : asset.heading;

          return {
            ...asset,
            coordinates: [nextLng, nextLat],
            heading: newHeading,
          };
        })
      );
    }, 1500);

    return () => clearInterval(interval);
  }, [isSimulating, simulationSpeed, routes]);

  return (
    <FleetContext.Provider
      value={{
        assets,
        routes,
        incidents,
        soteriaConsensus,
        activeIncident,
        metrics,
        selectedAsset,
        hoveredAsset,
        selectedIncident,
        isAddModalOpen,
        isNotificationSidebarOpen,
        addAssetDraftType,
        filterType,
        activeMapStyle,
        is3DMode,
        isSimulating,
        simulationSpeed,
        focusedCoordinates,
        selectAsset: setSelectedAsset,
        setHoveredAsset,
        selectIncident: setSelectedIncident,
        toggleNotificationSidebar,
        closeNotificationSidebar,
        openAddModal,
        closeAddModal,
        addAsset,
        updateAsset,
        deleteAsset,
        setFilterType,
        setActiveMapStyle,
        toggle3DMode,
        toggleSimulation,
        setSimulationSpeed,
        focusOnAsset,
      }}
    >
      {children}
    </FleetContext.Provider>
  );
};

export const useFleet = () => {
  const context = useContext(FleetContext);
  if (!context) {
    throw new Error('useFleet must be used within a FleetProvider');
  }
  return context;
};
