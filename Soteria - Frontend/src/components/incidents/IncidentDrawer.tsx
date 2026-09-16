import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { 
  AlertTriangle,
  ChevronUp,
  ChevronDown,
  Sparkles,
  X,
  Bell
} from 'lucide-react';
import { useFleet } from '../../context/FleetContext';
import { SOTERIA_BY_INCIDENT } from '../../data/mockFleetData';

export const IncidentDrawer: React.FC = () => {
  const { 
    incidents, 
    isNotificationSidebarOpen,
    closeNotificationSidebar,
    assets,
    activeIncident,
    focusOnAsset,
    selectIncident
  } = useFleet();
  
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const severityColor = (severity: string) =>
    severity === 'high' || severity === 'critical'
      ? 'var(--accent-rose)'
      : severity === 'medium'
      ? 'var(--accent-amber)'
      : 'var(--accent-emerald)';

  // Portal to <body> so the sidebar sits above the top navbar and all map overlays
  return createPortal(
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
                {incidents.length} active incidents in the network
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

            {/* Featured: opens the Agent Live Console in its own window */}
            <button
              type="button"
              className="btn-agent-console"
              onClick={() => window.open(`/console.html?incident=${activeIncident?.id ?? ''}`, 'soteria-agent-live-console', 'width=1440,height=900')}
            >
              <span className="btn-agent-console-dot" aria-hidden="true" />
              <span style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', flex: 1, minWidth: 0 }}>
                <span style={{ fontSize: '13px', fontWeight: 700 }}>Agent Live Console</span>
                <span style={{ fontSize: '10px', fontWeight: 400, opacity: 0.8 }}>
                  Watch every agent question, answer and approval flow
                </span>
              </span>
              <span aria-hidden="true" style={{ fontSize: '14px' }}>↗</span>
            </button>
            {/* Incident reports: one collapsible card per report, one open at a time */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {incidents.map((incident) => {
                const isOpen = expandedId === incident.id;
                const isActive = activeIncident?.id === incident.id;
                return (
                  <div
                    key={incident.id}
                    className="glass-card"
                    style={{
                      padding: 0,
                      overflow: 'hidden',
                      borderLeft: `3px solid ${severityColor(incident.severity)}`,
                      background: isActive ? 'rgba(255, 255, 255, 0.08)' : undefined,
                    }}
                  >
                    <button
                      type="button"
                      aria-expanded={isOpen}
                      aria-controls={`incident-details-${incident.id}`}
                      onClick={() => {
                        setExpandedId(isOpen ? null : incident.id);
                        selectIncident(incident);
                        const asset = assets.find(a => a.id === incident.assetId);
                        if (asset) focusOnAsset(asset);
                      }}
                      style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: '10px', padding: '10px 12px',
                        background: 'transparent', border: 'none', cursor: 'pointer', textAlign: 'left', color: 'inherit',
                      }}
                    >
                      <span
                        style={{
                          width: '18px', height: '18px', borderRadius: '50%', background: severityColor(incident.severity),
                          color: '#fff', fontSize: '9px', fontWeight: 700, display: 'flex', alignItems: 'center',
                          justifyContent: 'center', flexShrink: 0,
                        }}
                      >
                        !
                      </span>
                      <span style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '2px' }}>
                        <span style={{ display: 'flex', justifyContent: 'space-between', gap: '8px' }}>
                          <span style={{ fontSize: '12px', fontWeight: 600, color: '#ffffff' }}>{incident.assetName}</span>
                          <span style={{ fontSize: '9px', color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{incident.timeAgo}</span>
                        </span>
                        <span style={{ fontSize: '10px', color: 'var(--text-muted)' }}>
                          {incident.category} • Tier {incident.soteriaTier}
                        </span>
                      </span>
                      {isOpen ? <ChevronUp size={14} color="var(--text-muted)" /> : <ChevronDown size={14} color="var(--text-muted)" />}
                    </button>

                    {isOpen && (
                      <div id={`incident-details-${incident.id}`} style={{ padding: '0 12px 12px 40px' }}>
                        <div style={{ fontSize: '10px', color: 'var(--text-muted)' }}>{incident.reportedAt}</div>

                        <div style={{ marginTop: '4px', fontSize: '11px', color: 'var(--text-secondary)' }}>
                          {incident.title}
                        </div>

                        {/* Location / affected wagons */}
                        <div style={{ marginTop: '6px', fontSize: '11px', color: 'var(--text-muted)', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span>{incident.affectedLocations[0]}</span>
                          <span style={{ fontFamily: 'var(--font-mono)' }}>{incident.affectedCount}</span>
                        </div>

                        {/* Decision from the Soteria backend: what to do, how binding, who approved, why */}
                        {(() => {
                          const d = SOTERIA_BY_INCIDENT[incident.id]?.decision;
                          if (!d) {
                            return (
                              <div style={{ marginTop: '8px', display: 'flex', gap: '6px', fontSize: '11px', color: '#ffffff' }}>
                                <Sparkles size={13} color="#ffffff" />
                                <span><strong>Recommendation:</strong> {incident.recommendation}</span>
                              </div>
                            );
                          }
                          const accent = d.status === 'blocked' ? 'var(--accent-rose)'
                            : d.tier === 3 ? 'var(--accent-rose)' : d.tier === 2 ? 'var(--accent-amber)' : 'var(--accent-emerald)';
                          const row = { display: 'flex', justifyContent: 'space-between', gap: '8px' } as const;
                          return (
                            <div style={{ marginTop: '10px', borderRadius: '10px', border: `1px solid ${accent}`, background: 'rgba(255,255,255,0.05)', padding: '10px 12px', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                              <div style={{ fontSize: '9px', letterSpacing: '0.08em', fontWeight: 700, color: accent }}>
                                {d.status === 'blocked' ? `NO DECISION · ${d.code}` : 'DECISION'}
                              </div>
                              {d.measures.length > 0 && (
                                <ol style={{ margin: 0, paddingLeft: '18px', display: 'flex', flexDirection: 'column', gap: '2px' }}>
                                  {d.measures.map(m => (
                                    <li key={m.code} style={{ fontSize: '14px', fontWeight: 700, color: '#ffffff' }}>{m.label}</li>
                                  ))}
                                </ol>
                              )}
                              {d.status === 'decided' && (
                                <div style={{ fontSize: '10px', color: 'var(--text-secondary)', display: 'flex', flexDirection: 'column', gap: '3px' }}>
                                  <div style={row}><span>Authority</span><span style={{ color: accent, textAlign: 'right' }}>{d.tierLabel}</span></div>
                                  <div style={row}>
                                    <span>Approval</span>
                                    <span style={{ textAlign: 'right' }}>
                                      {d.keysNeeded ? `${d.grants?.length ?? 0}/${d.keysNeeded} keys ✓ ${d.grants?.join(', ')}` : 'not required'}
                                    </span>
                                  </div>
                                  <div style={row}>
                                    <span>Decided by</span>
                                    <span style={{ textAlign: 'right', fontFamily: 'var(--font-mono)', color: d.decidedBy === 'llm' ? 'var(--accent-emerald)' : 'var(--accent-amber)' }}>
                                      {d.decidedBy === 'llm' ? `${d.model} (LLM)` : d.decidedBy === 'policy_fallback' ? 'rule policy (model unreachable)' : 'rule policy'}
                                    </span>
                                  </div>
                                  <div style={row}><span>Reason</span><span>{d.reasonLabel}</span></div>
                                  {d.rationale && (
                                    <div style={{ fontStyle: 'italic', color: 'var(--text-secondary)', lineHeight: 1.4 }}>“{d.rationale}”</div>
                                  )}
                                  <div style={row}><span>Evidence</span><span>{d.coverage?.answered}/{d.coverage?.asked} answers</span></div>
                                  <div style={row}><span>Receipt</span><span style={{ fontFamily: 'var(--font-mono)' }}>{d.receiptHash}</span></div>
                                </div>
                              )}
                            </div>
                          );
                        })()}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
      </aside>
    </>,
    document.body
  );
};
