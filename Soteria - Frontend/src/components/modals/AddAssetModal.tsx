import React, { useState } from 'react';
import { X, Train, Truck, Building2, Plus, Sparkles, Thermometer, Compass, Gauge } from 'lucide-react';
import { useFleet } from '../../context/FleetContext';
import { AssetType, FleetAsset } from '../../types/fleet';
import { INITIAL_MAP_CENTER } from '../../data/mockFleetData';

export const AddAssetModal: React.FC = () => {
  const { isAddModalOpen, closeAddModal, addAssetDraftType, addAsset, routes } = useFleet();

  const [assetType, setAssetType] = useState<AssetType>(addAssetDraftType || 'train');
  const [name, setName] = useState('');
  const [category, setCategory] = useState<'Freight Train' | 'Electric Truck' | 'Container Truck' | 'Cargo Rail' | 'Logistics Hub'>('Freight Train');
  const [routeId, setRouteId] = useState(routes[0]?.id || 'route-l1');
  const [speedKmh, setSpeedKmh] = useState(85);
  const [cargoType, setCargoType] = useState<'Pharma / Cold Chain' | 'Automotive Parts' | 'Chemicals (Hazmat)' | 'High-Tech Electronics' | 'Bulk Freight'>('Pharma / Cold Chain');
  const [targetTempC, setTargetTempC] = useState(-18.0);
  const [loadPct, setLoadPct] = useState(82);

  if (!isAddModalOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const route = routes.find(r => r.id === routeId) || routes[0];
    
    // Add small random offset around selected route coordinate
    const baseCoords = route.coordinates[Math.floor(route.coordinates.length / 2)] || INITIAL_MAP_CENTER;
    const jitterLng = (Math.random() - 0.5) * 0.015;
    const jitterLat = (Math.random() - 0.5) * 0.015;

    const generatedName = name.trim() || (assetType === 'train' ? `Cargo Train ${Math.floor(1000 + Math.random() * 9000)}` : `Truck TR-${Math.floor(1000 + Math.random() * 9000)}`);

    addAsset({
      name: generatedName,
      type: assetType,
      category,
      status: 'online',
      statusText: 'In Transit — Operational',
      coordinates: [baseCoords[0] + jitterLng, baseCoords[1] + jitterLat],
      heading: Math.floor(Math.random() * 360),
      speedKmh,
      routeId,
      routeName: route.name,
      currentStation: 'Terminal West',
      nextStation: 'Central Station',
      estimatedArrivalMin: Math.floor(10 + Math.random() * 30),
      delayMin: 0,
      cargoType,
      cargoIntegrityPct: 100,
      targetTempC: cargoType === 'Pharma / Cold Chain' ? targetTempC : undefined,
      currentTempC: cargoType === 'Pharma / Cold Chain' ? targetTempC + 0.2 : undefined,
      loadPct,
      connectivity: {
        gps: true,
        lte: true,
        iotSensors: 12,
      },
      compartments: [
        { id: 'c-new-1', name: `Bay L ${Math.floor(10000 + Math.random() * 90000)}`, status: 'nominal', temp: targetTempC },
        { id: 'c-new-2', name: `Bay R ${Math.floor(10000 + Math.random() * 90000)}`, status: 'nominal', temp: targetTempC },
      ],
    });
  };

  return (
    <div className="modal-backdrop" onClick={closeAddModal}>
      <div 
        className="glass-panel"
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '500px',
          maxWidth: '92vw',
          padding: '24px',
          background: 'rgba(18, 18, 22, 0.96)',
          boxShadow: '0 24px 60px rgba(0, 0, 0, 0.85), 0 0 0 1px var(--border-glass) inset',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div 
              style={{ 
                width: '32px', 
                height: '32px', 
                borderRadius: '8px', 
                background: 'rgba(255, 255, 255, 0.12)', 
                border: '1px solid rgba(255, 255, 255, 0.25)', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                color: '#ffffff'
              }}
            >
              <Plus size={18} />
            </div>
            <div>
              <h3 style={{ fontSize: '17px', fontWeight: 600, color: '#ffffff' }}>
                Neue Flotteneinteilung hinzufügen
              </h3>
              <p style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                3D-Objekt wird sofort auf der Karte und in den Telemetriedaten aktiv
              </p>
            </div>
          </div>
          <button 
            onClick={closeAddModal}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
          
          {/* Unit Type Selection */}
          <div>
            <label style={{ fontSize: '12px', fontWeight: 500, color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>
              Fahrzeugtyp
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '10px' }}>
              <button
                type="button"
                className={`glass-card ${assetType === 'train' ? 'selected' : ''}`}
                onClick={() => { setAssetType('train'); setCategory('Freight Train'); }}
                style={{ padding: '12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
              >
                <Train size={22} color={assetType === 'train' ? 'var(--accent-cyan)' : 'var(--text-muted)'} />
                <span style={{ fontSize: '12px', fontWeight: 600 }}>Güterzug</span>
              </button>

              <button
                type="button"
                className={`glass-card ${assetType === 'truck' ? 'selected' : ''}`}
                onClick={() => { setAssetType('truck'); setCategory('Container Truck'); }}
                style={{ padding: '12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
              >
                <Truck size={22} color={assetType === 'truck' ? 'var(--accent-emerald)' : 'var(--text-muted)'} />
                <span style={{ fontSize: '12px', fontWeight: 600 }}>LKW / Reefer</span>
              </button>

              <button
                type="button"
                className={`glass-card ${assetType === 'depot' ? 'selected' : ''}`}
                onClick={() => { setAssetType('depot'); setCategory('Logistics Hub'); }}
                style={{ padding: '12px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
              >
                <Building2 size={22} color={assetType === 'depot' ? 'var(--accent-purple)' : 'var(--text-muted)'} />
                <span style={{ fontSize: '12px', fontWeight: 600 }}>Hub / Terminal</span>
              </button>
            </div>
          </div>

          {/* Name & Route */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                Kennung / Name
              </label>
              <input
                type="text"
                className="glass-input"
                style={{ width: '100%', borderRadius: '10px' }}
                placeholder={assetType === 'train' ? 'z.B. Train DB-8420' : 'z.B. Kühl-LKW TR-990'}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div>
              <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                Zugewiesene Route
              </label>
              <select
                className="glass-input"
                style={{ width: '100%', borderRadius: '10px', background: '#0e141f' }}
                value={routeId}
                onChange={(e) => setRouteId(e.target.value)}
              >
                {routes.map(r => (
                  <option key={r.id} value={r.id}>
                    {r.code} - {r.name}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Speed & Capacity Load */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                <span>Geschwindigkeit</span>
                <span style={{ color: 'var(--accent-cyan)', fontFamily: 'var(--font-mono)' }}>{speedKmh} km/h</span>
              </div>
              <input
                type="range"
                min="0"
                max="160"
                value={speedKmh}
                onChange={(e) => setSpeedKmh(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--accent-cyan)' }}
              />
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>
                <span>Auslastung (Load)</span>
                <span style={{ color: 'var(--accent-emerald)', fontFamily: 'var(--font-mono)' }}>{loadPct}%</span>
              </div>
              <input
                type="range"
                min="10"
                max="100"
                value={loadPct}
                onChange={(e) => setLoadPct(Number(e.target.value))}
                style={{ width: '100%', accentColor: 'var(--accent-emerald)' }}
              />
            </div>
          </div>

          {/* Cargo Type & Temperature */}
          <div style={{ display: 'grid', gridTemplateColumns: '1.2fr 0.8fr', gap: '12px' }}>
            <div>
              <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                Fracht-Kategorie
              </label>
              <select
                className="glass-input"
                style={{ width: '100%', borderRadius: '10px', background: '#0e141f' }}
                value={cargoType}
                onChange={(e) => setCargoType(e.target.value as any)}
              >
                <option value="Pharma / Cold Chain">Pharma / Cold Chain (-18°C)</option>
                <option value="Automotive Parts">Automotive Parts (Just-in-Time)</option>
                <option value="Chemicals (Hazmat)">Chemicals (Hazmat / Gefahrgut)</option>
                <option value="High-Tech Electronics">High-Tech Electronics</option>
                <option value="Bulk Freight">Bulk Freight</option>
              </select>
            </div>

            <div>
              <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                Kühlsollwert (°C)
              </label>
              <input
                type="number"
                step="0.5"
                className="glass-input"
                style={{ width: '100%', borderRadius: '10px', fontFamily: 'var(--font-mono)' }}
                value={targetTempC}
                onChange={(e) => setTargetTempC(Number(e.target.value))}
              />
            </div>
          </div>

          {/* Actions */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
            <button
              type="button"
              className="btn-glass"
              onClick={closeAddModal}
            >
              Abbrechen
            </button>
            <button
              type="submit"
              className="btn-glass btn-glass-primary"
              style={{ padding: '8px 24px' }}
            >
              <Sparkles size={15} />
              <span>Einheit Erstellen & Platzieren</span>
            </button>
          </div>

        </form>
      </div>
    </div>
  );
};
