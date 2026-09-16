import React, { useState, useEffect } from 'react';
import { 
  X, 
  Trash2, 
  Save, 
  Train, 
  Truck, 
  Thermometer, 
  Clock, 
  Gauge, 
  AlertTriangle,
  CheckCircle2,
  Sliders
} from 'lucide-react';
import { useFleet } from '../../context/FleetContext';
import { FleetAsset, AssetStatus } from '../../types/fleet';

interface EditAssetDrawerProps {
  onClose?: () => void;
}

export const EditAssetDrawer: React.FC<EditAssetDrawerProps> = ({ onClose }) => {
  const { selectedAsset, selectAsset, updateAsset, deleteAsset } = useFleet();

  const [speed, setSpeed] = useState(80);
  const [status, setStatus] = useState<AssetStatus>('online');
  const [delay, setDelay] = useState(0);
  const [temp, setTemp] = useState(-18.0);
  const [load, setLoad] = useState(80);

  useEffect(() => {
    if (selectedAsset) {
      setSpeed(selectedAsset.speedKmh);
      setStatus(selectedAsset.status);
      setDelay(selectedAsset.delayMin);
      setTemp(selectedAsset.currentTempC ?? -18.0);
      setLoad(selectedAsset.loadPct);
    }
  }, [selectedAsset]);

  if (!selectedAsset) return null;

  const handleClose = () => {
    if (onClose) onClose();
    else selectAsset(null);
  };

  const handleSave = () => {
    updateAsset(selectedAsset.id, {
      speedKmh: speed,
      status,
      statusText: status === 'warning' ? `Delayed — ${delay}m behind schedule` : status === 'offline' ? 'Offline / Telemetry Lost' : 'In Transit — Nominal',
      delayMin: delay,
      currentTempC: selectedAsset.targetTempC !== undefined ? temp : undefined,
      loadPct: load,
    });
    handleClose();
  };

  const handleDelete = () => {
    if (window.confirm(`Möchtest du "${selectedAsset.name}" wirklich von der Karte und aus der Flotte entfernen?`)) {
      deleteAsset(selectedAsset.id);
      handleClose();
    }
  };

  return (
    <div 
      className="glass-panel"
      style={{
        position: 'absolute',
        top: '84px',
        right: '400px',
        width: '320px',
        padding: '18px',
        pointerEvents: 'auto',
        zIndex: 40,
        boxShadow: '0 20px 48px rgba(0, 0, 0, 0.75), 0 0 0 1px var(--border-glass-bright) inset',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '14px' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Sliders size={16} color="#ffffff" />
          <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#ffffff' }}>
            Einheit Bearbeiten
          </h4>
        </div>
        <button 
          onClick={handleClose}
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
        >
          <X size={16} />
        </button>
      </div>

      {/* Asset Title & Category */}
      <div style={{ padding: '10px', background: 'rgba(255, 255, 255, 0.04)', borderRadius: '8px', marginBottom: '14px' }}>
        <div style={{ fontSize: '13px', fontWeight: 600, color: '#ffffff' }}>
          {selectedAsset.name}
        </div>
        <div style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          ID: {selectedAsset.id} • {selectedAsset.routeName}
        </div>
      </div>

      {/* Status Selector */}
      <div style={{ marginBottom: '12px' }}>
        <label style={{ fontSize: '11px', fontWeight: 500, color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
          Betriebsstatus
        </label>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '6px' }}>
          <button
            type="button"
            className={`glass-pill ${status === 'online' ? 'active' : ''}`}
            onClick={() => setStatus('online')}
            style={{ justifyContent: 'center', fontSize: '11px', padding: '6px 8px' }}
          >
            Online
          </button>
          <button
            type="button"
            className={`glass-pill ${status === 'warning' ? 'active' : ''}`}
            onClick={() => setStatus('warning')}
            style={{ justifyContent: 'center', fontSize: '11px', padding: '6px 8px', color: status === 'warning' ? 'var(--accent-amber)' : 'inherit' }}
          >
            Warnung
          </button>
          <button
            type="button"
            className={`glass-pill ${status === 'offline' ? 'active' : ''}`}
            onClick={() => setStatus('offline')}
            style={{ justifyContent: 'center', fontSize: '11px', padding: '6px 8px', color: status === 'offline' ? 'var(--accent-rose)' : 'inherit' }}
          >
            Offline
          </button>
        </div>
      </div>

      {/* Speed Slider */}
      <div style={{ marginBottom: '12px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
          <span>Geschwindigkeit:</span>
          <span style={{ color: '#ffffff', fontFamily: 'var(--font-mono)' }}>{speed} km/h</span>
        </div>
        <input 
          type="range" 
          min="0" 
          max="160" 
          value={speed} 
          onChange={(e) => setSpeed(Number(e.target.value))} 
          style={{ width: '100%', accentColor: '#ffffff' }}
        />
      </div>

      {/* Temperature if applicable */}
      {selectedAsset.currentTempC !== undefined && (
        <div style={{ marginBottom: '12px' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
            <span>Kühltemperatur:</span>
            <span style={{ color: temp > -16 ? 'var(--accent-rose)' : 'var(--accent-emerald)', fontFamily: 'var(--font-mono)' }}>{temp}°C</span>
          </div>
          <input 
            type="range" 
            min="-25" 
            max="10" 
            step="0.5"
            value={temp} 
            onChange={(e) => setTemp(Number(e.target.value))} 
            style={{ width: '100%', accentColor: temp > -16 ? 'var(--accent-rose)' : 'var(--accent-emerald)' }}
          />
        </div>
      )}

      {/* Delay / Schedule Variance */}
      <div style={{ marginBottom: '16px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '4px' }}>
          <span>Fahrplan-Verspätung:</span>
          <span style={{ color: delay > 0 ? 'var(--accent-amber)' : 'var(--accent-emerald)', fontFamily: 'var(--font-mono)' }}>
            {delay > 0 ? `+${delay}` : delay} min
          </span>
        </div>
        <input 
          type="range" 
          min="-10" 
          max="45" 
          value={delay} 
          onChange={(e) => setDelay(Number(e.target.value))} 
          style={{ width: '100%', accentColor: 'var(--accent-amber)' }}
        />
      </div>

      {/* Actions: Delete & Save */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
        <button 
          className="btn-glass btn-glass-danger"
          onClick={handleDelete}
          title="Fahrzeug löschen"
          style={{ padding: '6px 12px', fontSize: '12px' }}
        >
          <Trash2 size={13} />
          <span>Löschen</span>
        </button>

        <button 
          className="btn-glass btn-glass-primary"
          onClick={handleSave}
          style={{ padding: '6px 16px', fontSize: '12px' }}
        >
          <Save size={13} />
          <span>Speichern</span>
        </button>
      </div>
    </div>
  );
};
