import React, { useState } from 'react';
import { 
  AlertTriangle,
  ChevronUp,
  ChevronDown,
  Sparkles,
  ShieldCheck,
  ThermometerSnowflake,
  X,
  Bell
} from 'lucide-react';
import { useFleet } from '../../context/FleetContext';

export const IncidentDrawer: React.FC = () => {
  const { 
    incidents, 
    soteriaConsensus, 
    isNotificationSidebarOpen, 
    closeNotificationSidebar 
  } = useFleet();
  
  const [isReportsOpen, setIsReportsOpen] = useState(true);
  const [isConsensusOpen, setIsConsensusOpen] = useState(true);

  const severityColor = (severity: string) =>
    severity === 'high' || severity === 'critical'
      ? 'var(--accent-rose)'
      : severity === 'medium'
      ? 'var(--accent-amber)'
      : 'var(--accent-emerald)';

  return (
    <>
      {/* Click-outside backdrop: Closes notification sidebar automatically */}
      {isNotificationSidebarOpen && (
        <div 
          className="apple-notification-sidebar-backdrop" 
          onClick={closeNotificationSidebar} 
        />
      )}

      {/* Apple-style sidebar: Completely flush against right border with smooth slide animation */}
      <aside className={`apple-notification-sidebar ${isNotificationSidebarOpen ? 'open' : ''}`}>
        
        {/* Sidebar Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: '12px', borderBottom: '1px solid var(--border-glass)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div 
              style={{ 
                width: '32px', 
                height: '32px', 
                borderRadius: '8px', 
                background: 'rgba(239, 68, 68, 0.15)', 
                border: '1px solid rgba(239, 68, 68, 0.3)',
                display: 'flex', 
                alignItems: 'center', 
                justifyContent: 'center',
                color: 'var(--accent-rose)'
              }}
            >
              <Bell size={16} />
            </div>
            <div>
              <h3 style={{ fontSize: '15px', fontWeight: 600, color: '#ffffff' }}>
                Warnings & Incidents
              </h3>
              <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
                {incidents.length} aktive Vorfälle im Netzwerk
              </span>
            </div>
          </div>

          {/* Close X button */}
          <button 
            onClick={closeNotificationSidebar}
            style={{ 
              background: 'rgba(255, 255, 255, 0.06)', 
              border: '1px solid var(--border-subtle)', 
              borderRadius: '50%',
              width: '28px',
              height: '28px',
              color: 'var(--text-muted)', 
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transition: 'all 0.2s ease'
            }}
          >
            <X size={15} />
          </button>
        </div>
            {/* Einmeldungen: real incident reports, arrived one after another with date/time */}
            <div className="glass-card" style={{ padding: '12px' }}>
              <div
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', marginBottom: isReportsOpen ? '10px' : '0' }}
                onClick={() => setIsReportsOpen(!isReportsOpen)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                  <ThermometerSnowflake size={14} color="var(--accent-rose)" />
                  <span>Einmeldungen ({incidents.length})</span>
                </div>
                {isReportsOpen ? <ChevronUp size={14} color="var(--text-muted)" /> : <ChevronDown size={14} color="var(--text-muted)" />}
              </div>

              {isReportsOpen && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                  {incidents.map((incident) => (
                    <div key={incident.id} style={{ display: 'flex', alignItems: 'flex-start', gap: '8px' }}>
                      <div
                        style={{
                          width: '18px',
                          height: '18px',
                          borderRadius: '50%',
                          background: severityColor(incident.severity),
                          color: '#fff',
                          fontSize: '9px',
                          fontWeight: 700,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                          marginTop: '1px'
                        }}
                      >
                        !
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '8px' }}>
                          <span style={{ fontSize: '12px', fontWeight: 600, color: '#ffffff' }}>
                            {incident.assetName}
                          </span>
                          <span style={{ fontSize: '9px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>
                            {incident.timeAgo}
                          </span>
                        </div>

                        <div style={{ fontSize: '10px', color: 'var(--text-muted)', marginTop: '2px' }}>
                          {incident.reportedAt} • {incident.category}
                        </div>

                        <div style={{ marginTop: '4px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                          {incident.title}
                        </div>

                        {/* Location / affected wagons */}
                        <div style={{ marginTop: '6px', fontSize: '11px', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span>{incident.affectedLocations[0]}</span>
                          </div>
                          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                            <span style={{ fontFamily: 'var(--font-mono)' }}>{incident.affectedCount}</span>
                          </div>
                        </div>

                        {/* Recommended action pill */}
                        <div
                          style={{
                            marginTop: '8px',
                            padding: '8px 10px',
                            background: 'rgba(255, 255, 255, 0.08)',
                            border: '1px solid rgba(255, 255, 255, 0.18)',
                            borderRadius: '8px',
                            display: 'flex',
                            alignItems: 'center',
                            gap: '6px',
                            fontSize: '11px',
                            color: '#ffffff'
                          }}
                        >
                          <Sparkles size={13} color="#ffffff" />
                          <div>
                            <span style={{ fontWeight: 600 }}>Empfehlung:</span> {incident.recommendation}
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Accordion 3: Soteria Multi-Agent Need-to-Know Matrix */}
            <div className="glass-card" style={{ padding: '12px' }}>
              <div 
                style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', cursor: 'pointer', marginBottom: isConsensusOpen ? '10px' : '0' }}
                onClick={() => setIsConsensusOpen(!isConsensusOpen)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
                  <ShieldCheck size={14} color="var(--accent-emerald)" />
                  <span>Soteria Need-to-Know Matrix</span>
                </div>
                {isConsensusOpen ? <ChevronUp size={14} color="var(--text-muted)" /> : <ChevronDown size={14} color="var(--text-muted)" />}
              </div>

              {isConsensusOpen && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                  {soteriaConsensus.map((agent) => (
                    <div 
                      key={agent.role}
                      style={{
                        padding: '6px 8px',
                        background: 'rgba(255, 255, 255, 0.03)',
                        borderRadius: '6px',
                        display: 'flex',
                        flexDirection: 'column',
                        gap: '2px',
                        fontSize: '11px',
                        borderLeft: `2px solid ${
                          agent.status === 'verified' ? 'var(--accent-emerald)' : 'var(--accent-amber)'
                        }`
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <span style={{ fontWeight: 600, color: 'var(--text-primary)' }}>{agent.label}</span>
                        <span 
                          style={{ 
                            fontSize: '9px', 
                            padding: '1px 5px', 
                            borderRadius: '4px', 
                            background: agent.needToKnowVisibility === 'raw' 
                              ? 'rgba(255, 255, 255, 0.14)' 
                              : agent.needToKnowVisibility === 'ampel' 
                              ? 'rgba(245, 158, 11, 0.15)' 
                              : 'rgba(16, 185, 129, 0.15)',
                            color: agent.needToKnowVisibility === 'raw' 
                              ? '#ffffff' 
                              : agent.needToKnowVisibility === 'ampel' 
                              ? 'var(--accent-amber)' 
                              : 'var(--accent-emerald)',
                            fontFamily: 'var(--font-mono)'
                          }}
                        >
                          {agent.needToKnowVisibility.toUpperCase()}
                        </span>
                      </div>
                      <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                        {agent.lastFact}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
      </aside>
    </>
  );
};
