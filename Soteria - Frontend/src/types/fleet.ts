export type AssetType = 'train' | 'truck' | 'depot' | 'incident';
export type AssetStatus = 'online' | 'warning' | 'offline';

export interface SensorCompartment {
  id: string;
  name: string;
  temp?: number;
  pressure?: number;
  status: 'nominal' | 'warning' | 'critical';
}

export interface FleetAsset {
  id: string;
  name: string;
  type: AssetType;
  category: 'Freight Train' | 'Electric Truck' | 'Container Truck' | 'Cargo Rail' | 'Logistics Hub';
  status: AssetStatus;
  statusText: string;
  coordinates: [number, number]; // [longitude, latitude]
  altitude?: number;
  heading: number; // 0 - 360 degrees
  speedKmh: number;
  routeId: string;
  routeName: string;
  currentStation: string;
  nextStation: string;
  estimatedArrivalMin: number;
  delayMin: number; // positive = late, negative = early
  cargoType: 'Pharma / Cold Chain' | 'Automotive Parts' | 'Chemicals (Hazmat)' | 'High-Tech Electronics' | 'Bulk Freight';
  cargoIntegrityPct: number;
  targetTempC?: number;
  currentTempC?: number;
  loadPct: number;
  connectivity: {
    gps: boolean;
    lte: boolean;
    iotSensors: number;
  };
  compartments: SensorCompartment[];
  updatedAt: string;
}

export interface TransitRoute {
  id: string;
  code: string;
  name: string;
  type: 'rail' | 'road';
  color: string;
  coordinates: [number, number][];
  activeAssetsCount: number;
  scheduleVarianceMin: number;
  status: 'optimal' | 'delayed' | 'critical';
}

export interface IncidentAlert {
  id: string;
  title: string;
  category: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  assetId?: string;
  assetName?: string;
  routeCode?: string;
  timeAgo: string;
  timestamp: string;
  reportedAt: string;
  affectedCount: string;
  affectedLocations: string[];
  recommendation: string;
  soteriaTier: 1 | 2 | 3;
  marketSensitive: boolean;
}

export interface SoteriaConsensusItem {
  role: 'intake' | 'assessor' | 'legal' | 'supplier' | 'customer';
  label: string;
  status: 'verified' | 'pending' | 'restricted' | 'quarantined';
  needToKnowVisibility: 'raw' | 'ampel' | 'schwelle' | 'blocked';
  lastFact: string;
}

export interface FleetMetrics {
  totalVehicles: number;
  trainsCount: number;
  trucksCount: number;
  onlineCount: number;
  offlineCount: number;
  operationalEfficiencyPct: number;
  averageVarianceMin: number;
  wagonsInTransit: number;
  activeIncidentsCount: number;
}
