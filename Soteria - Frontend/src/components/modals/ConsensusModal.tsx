import React from 'react';
import { X, Shield, Lock, Eye, AlertCircle, CheckCircle2, Award } from 'lucide-react';
import { useFleet } from '../../context/FleetContext';

interface ConsensusModalProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ConsensusModal: React.FC<ConsensusModalProps> = ({ isOpen, onClose }) => {
  const { soteriaConsensus } = useFleet();

  if (!isOpen) return null;

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div 
        className="glass-panel" 
        onClick={(e) => e.stopPropagation()}
        style={{
          width: '740px',
          maxWidth: '94vw',
          maxHeight: '88vh',
          overflowY: 'auto',
          padding: '28px',
          background: 'rgba(18, 18, 22, 0.96)',
          boxShadow: '0 24px 64px rgba(0,0,0,0.85), 0 0 0 1px var(--border-glass-bright) inset',
        }}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div 
              style={{ 
                width: '36px', 
                height: '36px', 
                borderRadius: '10px', 
                background: 'linear-gradient(135deg, var(--accent-emerald), var(--accent-cyan))', 
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                boxShadow: '0 0 20px var(--accent-emerald-glow)'
              }}
            >
              <Shield size={20} color="#ffffff" />
            </div>
            <div>
              <h3 style={{ fontSize: '18px', fontWeight: 600, color: '#ffffff' }}>
                Soteria — Need-to-Know Multi-Agent Matrix
              </h3>
              <p style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                Decision-making on freight damage without disclosing secrets
              </p>
            </div>
          </div>
          <button 
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer' }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Matrix Explainer Banner */}
        <div 
          style={{ 
            padding: '14px 18px', 
            background: 'rgba(255, 255, 255, 0.06)', 
            border: '1px solid rgba(255, 255, 255, 0.14)', 
            borderRadius: '12px',
            marginBottom: '20px',
            fontSize: '12px',
            color: 'var(--text-secondary)',
            lineHeight: 1.5
          }}
        >
          <strong style={{ color: '#ffffff' }}>Zero-Knowledge Protokoll:</strong> Kein Beteiligter darf alles wissen. 
          The assessor decides on traffic lights and thresholds, without ever seeing raw values such as company stock levels or contract penalties in plain text.
        </div>

        {/* Matrix Table */}
        <div style={{ width: '100%', overflowX: 'auto', marginBottom: '24px' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--border-glass)', color: 'var(--text-muted)', textAlign: 'left' }}>
                <th style={{ padding: '10px' }}>Datenfeld</th>
                <th style={{ padding: '10px', textAlign: 'center' }}>Intake</th>
                <th style={{ padding: '10px', textAlign: 'center' }}>Assessor</th>
                <th style={{ padding: '10px', textAlign: 'center' }}>Legal</th>
                <th style={{ padding: '10px', textAlign: 'center' }}>Supplier</th>
                <th style={{ padding: '10px', textAlign: 'center' }}>Customer</th>
              </tr>
            </thead>
            <tbody>
              {[
                { field: 'cargo_class', intake: 'grob', assessor: 'grob', legal: '—', supplier: 'RAW', customer: 'RAW' },
                { field: 'temperature_curve', intake: 'RAW', assessor: 'AMPEL', legal: '—', supplier: 'RAW', customer: 'RAW' },
                { field: 'customer_stock', intake: '—', assessor: 'AMPEL', legal: '—', supplier: '—', customer: 'RAW' },
                { field: 'contract_penalty', intake: '—', assessor: 'SCHWELLE', legal: 'RAW', supplier: '—', customer: '—' },
                { field: 'route_weakness', intake: '—', assessor: 'AMPEL', legal: '—', supplier: '—', customer: '—' },
                { field: 'replacement_avail', intake: '—', assessor: 'AMPEL', legal: '—', supplier: 'RAW', customer: 'AMPEL' },
              ].map((row, idx) => (
                <tr key={idx} style={{ borderBottom: '1px solid rgba(255,255,255,0.04)' }}>
                  <td style={{ padding: '10px', fontFamily: 'var(--font-mono)', color: 'var(--text-secondary)' }}>
                    {row.field}
                  </td>
                  <td style={{ padding: '10px', textAlign: 'center', color: row.intake === '—' ? 'var(--text-dim)' : 'var(--text-secondary)' }}>{row.intake}</td>
                  <td style={{ padding: '10px', textAlign: 'center', fontWeight: 600, color: row.assessor === 'AMPEL' ? 'var(--accent-amber)' : 'var(--accent-emerald)' }}>{row.assessor}</td>
                  <td style={{ padding: '10px', textAlign: 'center', color: row.legal === '—' ? 'var(--text-dim)' : 'var(--text-secondary)' }}>{row.legal}</td>
                  <td style={{ padding: '10px', textAlign: 'center', color: row.supplier === '—' ? 'var(--text-dim)' : 'var(--text-secondary)' }}>{row.supplier}</td>
                  <td style={{ padding: '10px', textAlign: 'center', color: row.customer === '—' ? 'var(--text-dim)' : 'var(--text-secondary)' }}>{row.customer}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Live Consensus Agent Verdicts */}
        <h4 style={{ fontSize: '14px', fontWeight: 600, color: '#ffffff', marginBottom: '12px' }}>
          Aktueller Vorfalls-Konsens (#SR-884)
        </h4>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '10px' }}>
          {soteriaConsensus.map((agent) => (
            <div 
              key={agent.role}
              className="glass-card"
              style={{ padding: '12px 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                <CheckCircle2 size={16} color="var(--accent-emerald)" />
                <div>
                  <span style={{ fontSize: '13px', fontWeight: 600, color: '#ffffff' }}>
                    {agent.label}
                  </span>
                  <p style={{ fontSize: '12px', color: 'var(--text-muted)', marginTop: '2px' }}>
                    {agent.lastFact}
                  </p>
                </div>
              </div>
              <span 
                style={{ 
                  padding: '4px 10px', 
                  borderRadius: '6px', 
                  background: 'rgba(255,255,255,0.06)', 
                  fontSize: '11px',
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--accent-cyan)'
                }}
              >
                STATUS: VERIFIED
              </span>
            </div>
          ))}
        </div>

        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: '24px' }}>
          <button className="btn-glass btn-glass-primary" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
