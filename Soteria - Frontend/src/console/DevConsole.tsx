import React, { useEffect, useMemo, useRef, useState } from 'react';
import { SOTERIA_BY_INCIDENT, SoteriaEvent } from '../data/mockFleetData';

// Process monitor: replays the recorded Soteria event stream of an incident as a flow diagram.
// Source is the event stream exported by Soteria/scripts/export_frontend.py (recorded run, not a live socket).

type NodeId = 'incident' | 'assessor' | 'carrier' | 'supplier' | 'customer' | 'quarantine' | 'coverage' | 'model' | 'grants' | 'decision' | 'receipts';

const NODES: Record<NodeId, { x: number; y: number; label: string; sub: string }> = {
  incident:   { x: 80,   y: 290, label: 'Report',       sub: 'incident.open' },
  assessor:   { x: 270,  y: 290, label: 'Assessor',     sub: 'ServerApp' },
  carrier:    { x: 490,  y: 170, label: 'Carrier',      sub: 'SuperNode · intake, legal' },
  supplier:   { x: 490,  y: 290, label: 'Supplier',     sub: 'SuperNode' },
  customer:   { x: 490,  y: 410, label: 'Customer',     sub: 'SuperNode' },
  quarantine: { x: 490,  y: 55,  label: 'Quarantine',   sub: 'Market-sensitive' },
  coverage:   { x: 700,  y: 290, label: 'Coverage',     sub: 'coverage' },
  model:      { x: 870,  y: 150, label: 'LLM',          sub: 'Endeavor · AgentApp' },
  grants:     { x: 870,  y: 290, label: 'Approval',     sub: 'Human keys' },
  decision:   { x: 1040, y: 290, label: 'Decision',     sub: 'decision' },
  receipts:   { x: 1040, y: 430, label: 'Receipts',     sub: 'Hash chain' },
};

const EDGES: [NodeId, NodeId][] = [
  ['incident', 'assessor'],
  ['assessor', 'carrier'], ['assessor', 'supplier'], ['assessor', 'customer'],
  ['carrier', 'quarantine'],
  ['carrier', 'coverage'], ['supplier', 'coverage'], ['customer', 'coverage'],
  ['coverage', 'model'], ['model', 'grants'], ['grants', 'decision'], ['decision', 'receipts'],
];

const PARTY_OF_ROLE: Record<string, NodeId> = { intake: 'carrier', legal: 'carrier', supplier: 'supplier', customer: 'customer' };
const PARTY_OF_TYPE: Record<string, NodeId> = { carrier: 'carrier', supplier: 'supplier', customer: 'customer' };

/** Which node an event belongs to, and which edge it travels on. */
function locate(events: SoteriaEvent[], i: number): { node: NodeId; edge?: [NodeId, NodeId] } {
  const e = events[i];
  switch (e.type) {
    case 'soteria.incident.open': return { node: 'incident', edge: ['incident', 'assessor'] };
    case 'soteria.role.ready': return { node: PARTY_OF_TYPE[String(e.party_type)] ?? 'assessor' };
    case 'soteria.ask': {
      const answer = events.slice(i + 1).find(n => n.type === 'soteria.fact' && n.field === e.field);
      const party = answer ? PARTY_OF_ROLE[String(answer.role)] : undefined;
      return party ? { node: 'assessor', edge: ['assessor', party] } : { node: 'assessor' };
    }
    case 'soteria.fact': {
      const party = PARTY_OF_ROLE[String(e.role)] ?? 'assessor';
      return { node: party, edge: ['assessor', party] };
    }
    case 'collab.taint':
    case 'soteria.quarantine': return { node: 'quarantine', edge: ['carrier', 'quarantine'] };
    case 'soteria.coverage': return { node: 'coverage' };
    case 'soteria.grant.required':
    case 'soteria.grant.given': return { node: 'grants', edge: ['model', 'grants'] };
    case 'soteria.model.request':
    case 'soteria.model.decision': return { node: 'model', edge: ['coverage', 'model'] };
    case 'soteria.decision':
    case 'soteria.no_decision': return { node: 'decision', edge: ['grants', 'decision'] };
    case 'soteria.receipt':
    case 'soteria.done': return { node: 'receipts' };
    default: return { node: 'assessor' };
  }
}

function summary(e: SoteriaEvent): string {
  switch (e.type) {
    case 'soteria.incident.open': return `${e.train_id} · ${e.severity} · ${e.location}`;
    case 'soteria.role.ready': return `${e.party_id} online (${(e.speaks_as as string[]).join(', ')})`;
    case 'soteria.ask': return `asks ${e.field} → ${e.visibility}`;
    case 'soteria.fact': return `${e.role}: ${e.field} = ${String(e.value)}${e.scope ? ` (${e.scope})` : ''}`;
    case 'soteria.receipt': return `#${e.seq_in_chain} ${e.kind} ${e.hash}`;
    case 'soteria.quarantine': return `blocked: ${(e.blocked_channels as string[]).join(', ')}`;
    case 'soteria.coverage': return `${e.answered}/${e.asked} answered`;
    case 'soteria.grant.required': return `Tier ${e.tier}: ${e.keys_needed} key(s) required`;
    case 'soteria.grant.given': return `${e.human_id} → ${e.keys_have}/${e.keys_needed}`;
    case 'soteria.model.request': return `asks ${e.model} on ${e.federation} (${(e.signals as string[]).length} signals)`;
    case 'soteria.model.decision': return `${e.decided_by === 'llm' ? e.model : 'rule policy'} → ${(e.measures as string[]).join(', ')} (${e.latency_seconds}s)${e.error ? ` · ${e.error}` : ''}`;
    case 'soteria.decision': return `${(e.measures as string[]).join(', ')} · Tier ${e.tier} · by ${e.decided_by === 'llm' ? e.model : 'rule policy'}`;
    case 'soteria.no_decision': return `blocked: ${e.code}`;
    case 'soteria.done': return `done · chain verified: ${e.receipt_chain_verified}`;
    default: return '';
  }
}

const COLOR = { idle: '#3f3f46', seen: '#38bdf8', active: '#ffffff', red: '#ef4444', green: '#10b981', amber: '#f59e0b' };
const incidentIds = Object.keys(SOTERIA_BY_INCIDENT);

// Live bridge (Soteria/scripts/bridge.py): runs the incident on the real federation and streams its events
const BRIDGE_URL = (import.meta.env.VITE_BRIDGE_URL as string | undefined) ?? 'http://127.0.0.1:8765';
type LiveStatus = 'off' | 'connecting' | 'running' | 'finished' | 'error';

export const DevConsole: React.FC = () => {
  const initial = new URLSearchParams(window.location.search).get('incident');
  const [incidentId, setIncidentId] = useState<string>(initial && SOTERIA_BY_INCIDENT[initial] ? initial : incidentIds[incidentIds.length - 1]);
  const [followOperator, setFollowOperator] = useState(true);
  const [cursor, setCursor] = useState(0);            // number of events already played
  const [playing, setPlaying] = useState(true);
  const [speed, setSpeed] = useState(1);
  const [focusNode, setFocusNode] = useState<NodeId | null>(null);
  const [openSeq, setOpenSeq] = useState<number | null>(null);

  const [live, setLive] = useState<LiveStatus>('off');
  const [liveEvents, setLiveEvents] = useState<SoteriaEvent[]>([]);
  const [bridgeLog, setBridgeLog] = useState<string[]>([]);
  const [liveDetail, setLiveDetail] = useState('');
  const sourceRef = useRef<EventSource | null>(null);

  const entry = SOTERIA_BY_INCIDENT[incidentId];
  const isLive = live !== 'off';
  const events = isLive ? liveEvents : entry.events;

  const stopLive = () => { sourceRef.current?.close(); sourceRef.current = null; };
  const restart = (id: string) => {
    stopLive(); setLive('off'); setLiveEvents([]);
    setIncidentId(id); setCursor(0); setPlaying(true); setFocusNode(null); setOpenSeq(null);
  };

  const runLive = () => {
    stopLive();
    setLive('connecting'); setLiveEvents([]); setBridgeLog([]); setLiveDetail('');
    setCursor(0); setPlaying(false); setFocusNode(null); setOpenSeq(null); setFollowOperator(false);
    // One nonce per click: the bridge refuses a reused nonce, so an auto-reconnect can never start a second run
    const nonce = typeof crypto !== 'undefined' && 'randomUUID' in crypto ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
    const source = new EventSource(`${BRIDGE_URL}/api/run/${entry.caseId}/stream?run=${encodeURIComponent(nonce)}`);
    sourceRef.current = source;
    source.onmessage = (msg) => {
      let e: SoteriaEvent;
      try { e = JSON.parse(msg.data); } catch { return; }
      if (e.type === 'soteria.bridge.log') {
        setBridgeLog(prev => [...prev.slice(-199), `[${e.source}] ${e.line}`]);
      } else if (e.type === 'soteria.bridge.stage') {
        setLive('running'); setLiveDetail(String(e.detail ?? e.stage));
        setBridgeLog(prev => [...prev.slice(-199), `▶ ${e.stage}: ${e.detail}`]);
      } else if (e.type === 'soteria.bridge.finished') {
        setLive('finished'); setLiveDetail(`${e.events} events from the federation in ${e.elapsed_seconds}s`);
        stopLive();   // close explicitly, otherwise EventSource reconnects and starts a second run
      } else if (e.type === 'soteria.bridge.error') {
        setLive('error'); setLiveDetail(`${e.stage}: ${e.detail}`);
        stopLive();
      } else {
        setLiveEvents(prev => [...prev, e]);
      }
    };
    source.addEventListener('end', () => { setLive(prev => (prev === 'error' ? prev : 'finished')); stopLive(); });
    source.onerror = () => {
      if (!sourceRef.current) return;
      setLive(prev => (prev === 'finished' ? prev : 'error'));
      setLiveDetail(d => d || `bridge not reachable at ${BRIDGE_URL} — start it with: uv run python scripts/bridge.py`);
      stopLive();
    };
  };

  useEffect(() => stopLive, []);

  // Live mode follows the stream: always show every event received so far
  useEffect(() => { if (isLive) setCursor(liveEvents.length); }, [isLive, liveEvents.length]);

  // Follow the operator's selection in the main dashboard
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('soteria-console');
    channel.onmessage = (msg) => {
      const id = msg.data?.incidentId;
      if (followOperator && !sourceRef.current && id && SOTERIA_BY_INCIDENT[id] && id !== incidentId) restart(id);
    };
    return () => channel.close();
  }, [followOperator, incidentId]);

  // Playback clock
  useEffect(() => {
    if (isLive || !playing || cursor >= events.length) return;
    const timer = setTimeout(() => setCursor(c => c + 1), 320 / speed);
    return () => clearTimeout(timer);
  }, [isLive, playing, cursor, speed, events.length]);

  const located = useMemo(() => events.map((_, i) => locate(events, i)), [events]);
  const played = events.slice(0, cursor);
  const current = cursor > 0 ? located[cursor - 1] : null;

  const nodeCount = (id: NodeId) => located.slice(0, cursor).filter(l => l.node === id).length;
  const quarantined = played.some(e => e.type === 'soteria.quarantine');
  const decided = played.find(e => e.type === 'soteria.decision' || e.type === 'soteria.no_decision');
  const grantGiven = played.filter(e => e.type === 'soteria.grant.given').length;
  const asks = played.filter(e => e.type === 'soteria.ask').length;
  const modelEvent = played.find(e => e.type === 'soteria.model.decision');
  const grantRequired = played.find(e => e.type === 'soteria.grant.required');
  const doneEvent = played.find(e => e.type === 'soteria.done');
  const keysNeeded = played.find(e => e.type === 'soteria.grant.required')?.keys_needed ?? (isLive ? '?' : entry.decision.keysNeeded ?? 0);
  const facts = played.filter(e => e.type === 'soteria.fact').length;

  const nodeColor = (id: NodeId) => {
    if (id === 'quarantine' && quarantined) return COLOR.red;
    if (id === 'decision' && decided) return decided.type === 'soteria.decision' ? COLOR.green : COLOR.red;
    return nodeCount(id) > 0 ? COLOR.seen : COLOR.idle;
  };

  const log = played
    .map((e, i) => ({ e, loc: located[i] }))
    .filter(({ loc }) => !focusNode || loc.node === focusNode)
    .reverse();

  const btn: React.CSSProperties = {
    background: 'rgba(255,255,255,0.08)', border: '1px solid rgba(255,255,255,0.18)', color: '#fff',
    borderRadius: '8px', padding: '6px 12px', cursor: 'pointer', fontSize: '12px',
  };

  return (
    <div style={{ minHeight: '100vh', background: '#0a0a0c', color: '#e4e4e7', fontFamily: 'var(--font-sans, system-ui)', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <header style={{ display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 20px', borderBottom: '1px solid rgba(255,255,255,0.1)', flexWrap: 'wrap' }}>
        <strong style={{ fontSize: '15px', color: '#fff' }}>Soteria Agent Live Console</strong>
        <span style={{
          fontSize: '11px', fontWeight: 700, padding: '3px 8px', borderRadius: '999px',
          background: isLive ? 'rgba(239,68,68,0.18)' : 'rgba(255,255,255,0.08)',
          color: isLive ? '#fca5a5' : '#a1a1aa', border: `1px solid ${isLive ? 'rgba(239,68,68,0.5)' : 'rgba(255,255,255,0.15)'}`,
        }}>
          {isLive ? `● LIVE · Flower federation · ${live}` : 'REPLAY · recorded run'}
        </span>
        {liveDetail && <span style={{ fontSize: '11px', color: live === 'error' ? COLOR.red : '#a1a1aa' }}>{liveDetail}</span>}
        <div style={{ display: 'flex', gap: '6px', marginLeft: 'auto' }}>
          {incidentIds.map(id => (
            <button key={id} type="button" onClick={() => { setFollowOperator(false); restart(id); }}
              style={{ ...btn, background: id === incidentId ? 'rgba(56,189,248,0.25)' : btn.background }}>
              {SOTERIA_BY_INCIDENT[id].trainId}
            </button>
          ))}
        </div>
        <label style={{ fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <input type="checkbox" checked={followOperator} onChange={e => setFollowOperator(e.target.checked)} />
          Follow operator
        </label>
      </header>

      {/* Controls + KPIs */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '10px 20px', flexWrap: 'wrap' }}>
        <button type="button" onClick={runLive} disabled={live === 'connecting' || live === 'running'}
          style={{ ...btn, background: 'rgba(239,68,68,0.22)', borderColor: 'rgba(239,68,68,0.55)', fontWeight: 700,
                   opacity: live === 'connecting' || live === 'running' ? 0.6 : 1 }}>
          {live === 'connecting' || live === 'running' ? '● Running on federation…' : `● Run live (${entry.caseId})`}
        </button>
        {isLive && <button type="button" style={btn} onClick={() => restart(incidentId)}>Back to replay</button>}
        <button type="button" style={btn} disabled={isLive} onClick={() => { if (cursor >= events.length) setCursor(0); setPlaying(p => !p); }}>
          {playing && cursor < events.length ? '⏸ Pause' : '▶ Play'}
        </button>
        <button type="button" style={btn} onClick={() => { setPlaying(false); setCursor(c => Math.min(events.length, c + 1)); }}>⏭ Step</button>
        <button type="button" style={btn} onClick={() => { setPlaying(false); setCursor(events.length); }}>⏩ End</button>
        <button type="button" style={btn} onClick={() => restart(incidentId)}>⟲ Restart</button>
        <select value={speed} onChange={e => setSpeed(Number(e.target.value))} style={{ ...btn, padding: '6px' }}>
          {[0.5, 1, 2, 4].map(s => <option key={s} value={s}>{s}×</option>)}
        </select>
        <input type="range" min={0} max={events.length} value={cursor}
          onChange={e => { setPlaying(false); setCursor(Number(e.target.value)); }} style={{ flex: 1, minWidth: '160px' }} />
        <span style={{ fontFamily: 'var(--font-mono, monospace)', fontSize: '12px' }}>{cursor}/{events.length}</span>
      </div>
      <div style={{ display: 'flex', gap: '10px', padding: '0 20px 10px', flexWrap: 'wrap', fontSize: '12px' }}>
        {[
          ['Questions', `${asks}`],
          ['Answers', `${facts}`],
          ['Quarantine', quarantined ? 'ACTIVE' : '—'],
          ['Model', modelEvent ? (modelEvent.decided_by === 'llm' ? String(modelEvent.model) : 'rule policy (fallback)') : '—'],
          ['Keys', `${grantGiven}/${keysNeeded}`],
          ['Decision', decided ? (decided.type === 'soteria.decision' ? (decided.measures as string[]).join(', ') : `blocked (${decided.code})`) : 'running…'],
        ].map(([k, v]) => (
          <div key={k} style={{ padding: '6px 12px', borderRadius: '8px', background: 'rgba(255,255,255,0.05)', border: '1px solid rgba(255,255,255,0.1)' }}>
            <span style={{ color: '#a1a1aa' }}>{k}: </span>
            <strong style={{ color: k === 'Quarantine' && quarantined ? COLOR.red : '#fff' }}>{v}</strong>
          </div>
        ))}
      </div>

      {live === 'error' && (
        <div role="alert" style={{ margin: '0 20px 10px', padding: '10px 14px', borderRadius: '10px', background: 'rgba(239,68,68,0.15)', border: '1px solid rgba(239,68,68,0.6)', color: '#fecaca', fontSize: '12px' }}>
          <strong>Live run failed.</strong> {liveDetail} — nothing below is a recording; use “Back to replay” to show the recorded run.
        </div>
      )}
      {isLive && bridgeLog.length > 0 && (
        <details style={{ margin: '0 20px 10px', fontSize: '11px' }} open={live !== 'finished'}>
          <summary style={{ cursor: 'pointer', color: '#a1a1aa' }}>Infrastructure: real SuperLink / SuperNode / flwr output ({bridgeLog.length} lines)</summary>
          <pre style={{ margin: '6px 0 0', maxHeight: '140px', overflowY: 'auto', padding: '8px 10px', background: 'rgba(255,255,255,0.03)', borderRadius: '8px', color: '#a1a1aa', whiteSpace: 'pre-wrap' }}>
            {bridgeLog.slice(-60).join('\n')}
          </pre>
        </details>
      )}

      {/* Flow diagram + event log */}
      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 420px', gap: '12px', padding: '0 20px 20px', flex: 1, minHeight: 0 }}>
        <div style={{ borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.02)' }}>
          <svg viewBox="0 0 1130 490" style={{ width: '100%', height: 'auto', display: 'block' }} role="img" aria-label="Incident process flow">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                <path d="M 0 0 L 10 5 L 0 10 z" fill="#71717a" />
              </marker>
            </defs>
            {EDGES.map(([a, b]) => {
              const hot = current?.edge && current.edge[0] === a && current.edge[1] === b;
              return (
                <line key={`${a}-${b}`} x1={NODES[a].x} y1={NODES[a].y} x2={NODES[b].x} y2={NODES[b].y}
                  stroke={hot ? COLOR.active : '#3f3f46'} strokeWidth={hot ? 3 : 1.5}
                  strokeDasharray={hot ? '6 4' : undefined} markerEnd="url(#arrow)">
                  {hot && <animate attributeName="stroke-dashoffset" from="20" to="0" dur="0.4s" repeatCount="indefinite" />}
                </line>
              );
            })}
            {(Object.keys(NODES) as NodeId[]).map(id => {
              const n = NODES[id];
              const isCurrent = current?.node === id;
              const color = nodeColor(id);
              const count = nodeCount(id);
              return (
                <g key={id} transform={`translate(${n.x - 70}, ${n.y - 32})`} style={{ cursor: 'pointer' }}
                  onClick={() => setFocusNode(focusNode === id ? null : id)}>
                  <rect width={140} height={64} rx={12} fill={isCurrent ? 'rgba(255,255,255,0.12)' : '#18181b'}
                    stroke={focusNode === id ? '#ffffff' : color} strokeWidth={isCurrent || focusNode === id ? 3 : 1.5} />
                  <text x={70} y={26} textAnchor="middle" fill="#fff" fontSize={14} fontWeight={600}>{n.label}</text>
                  <text x={70} y={44} textAnchor="middle" fill="#a1a1aa" fontSize={10}>{n.sub}</text>
                  {count > 0 && (
                    <g transform="translate(124, -8)">
                      <circle r={11} fill={color} />
                      <text textAnchor="middle" y={4} fontSize={10} fill="#0a0a0c" fontWeight={700}>{count}</text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
          {/* The decision itself: what the agents concluded, and who decided it */}
          <div style={{ margin: '0 16px 12px', padding: '12px 14px', borderRadius: '10px',
                        border: `1px solid ${decided ? (decided.type === 'soteria.decision' ? COLOR.green : COLOR.red) : 'rgba(255,255,255,0.12)'}`,
                        background: decided ? 'rgba(16,185,129,0.08)' : 'rgba(255,255,255,0.03)' }}>
            {!decided ? (
              <span style={{ fontSize: '12px', color: '#a1a1aa' }}>
                Decision pending — {asks} asked, {facts} answered{modelEvent ? ', model answered' : ''}…
              </span>
            ) : decided.type === 'soteria.no_decision' ? (
              <div style={{ color: COLOR.red }}>
                <div style={{ fontSize: '10px', letterSpacing: '0.08em', fontWeight: 700 }}>NO DECISION</div>
                <div style={{ fontSize: '18px', fontWeight: 700 }}>{String(decided.code)}</div>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: '18px', flexWrap: 'wrap', alignItems: 'flex-start' }}>
                <div style={{ minWidth: '240px' }}>
                  <div style={{ fontSize: '10px', letterSpacing: '0.08em', fontWeight: 700, color: COLOR.green }}>DECISION</div>
                  <div style={{ fontSize: '20px', fontWeight: 700, color: '#fff', lineHeight: 1.25 }}>
                    {(decided.measures as string[]).join(' + ')}
                  </div>
                  <div style={{ fontSize: '11px', color: '#a1a1aa', marginTop: '2px' }}>
                    Tier {String(decided.tier)} · {String(decided.reason_code)} ·{' '}
                    {(decided.grants as string[]).length
                      ? `${(decided.grants as string[]).length}/${String(grantRequired?.keys_needed ?? '?')} human keys ✓`
                      : 'no approval required'}
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: '260px', fontSize: '11px', color: '#d4d4d8' }}>
                  <div>
                    <span style={{ color: '#a1a1aa' }}>Decided by: </span>
                    <strong style={{ color: modelEvent?.decided_by === 'llm' ? COLOR.green : COLOR.amber }}>
                      {modelEvent?.decided_by === 'llm' ? `${String(modelEvent.model)} (LLM)` : 'rule policy (model unavailable)'}
                    </strong>
                    {modelEvent?.error ? <span style={{ color: COLOR.red }}> · {String(modelEvent.error)}</span> : null}
                    {(modelEvent?.floor_added as string[] | undefined)?.length
                      ? <span style={{ color: COLOR.amber }}> · safety floor added {(modelEvent!.floor_added as string[]).join(', ')}</span> : null}
                  </div>
                  {modelEvent?.rationale ? (
                    <div style={{ fontStyle: 'italic', marginTop: '4px' }}>“{String(modelEvent.rationale)}”</div>
                  ) : null}
                  <div style={{ marginTop: '4px', fontFamily: 'var(--font-mono, monospace)', color: '#a1a1aa' }}>
                    receipt {String(decided.receipt_hash)}
                    {doneEvent ? ` · chain ${doneEvent.receipt_chain_verified ? 'verified' : 'BROKEN'} · ${String(doneEvent.elapsed_seconds)}s` : ''}
                    {quarantined ? ' · quarantine active' : ''}
                  </div>
                </div>
              </div>
            )}
          </div>
          <p style={{ margin: 0, padding: '0 16px 12px', fontSize: '11px', color: '#71717a' }}>
            Click a node to filter the log. Each party keeps its raw data; only traffic lights, thresholds and coarse classes travel along the edges.
          </p>
        </div>

        <div style={{ borderRadius: '12px', border: '1px solid rgba(255,255,255,0.1)', background: 'rgba(255,255,255,0.02)', display: 'flex', flexDirection: 'column', minHeight: 0, maxHeight: 'calc(100vh - 170px)' }}>
          <div style={{ padding: '10px 14px', borderBottom: '1px solid rgba(255,255,255,0.1)', fontSize: '12px', display: 'flex', justifyContent: 'space-between' }}>
            <strong>Event log {focusNode ? `· ${NODES[focusNode].label}` : ''}</strong>
            {focusNode && <button type="button" style={{ ...btn, padding: '2px 8px', fontSize: '11px' }} onClick={() => setFocusNode(null)}>Clear filter</button>}
          </div>
          <div style={{ overflowY: 'auto', flex: 1 }}>
            {log.map(({ e, loc }) => (
              <div key={e.seq} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                <button type="button" onClick={() => setOpenSeq(openSeq === e.seq ? null : e.seq)} aria-expanded={openSeq === e.seq}
                  style={{ width: '100%', textAlign: 'left', background: 'transparent', border: 'none', color: 'inherit', cursor: 'pointer', padding: '7px 14px', display: 'flex', gap: '8px', fontSize: '11px' }}>
                  <span style={{ fontFamily: 'var(--font-mono, monospace)', color: '#71717a', width: '28px' }}>{e.seq}</span>
                  <span style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ color: e.type === 'soteria.quarantine' || e.type === 'soteria.refusal' ? COLOR.red : e.type === 'soteria.decision' ? COLOR.green : COLOR.seen }}>
                      {e.type.replace('soteria.', '')}
                    </span>
                    <span style={{ color: '#71717a' }}> · {NODES[loc.node].label}</span>
                    <div style={{ color: '#d4d4d8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{summary(e)}</div>
                  </span>
                </button>
                {openSeq === e.seq && (
                  <pre style={{ margin: 0, padding: '8px 14px 10px 50px', fontSize: '10px', color: '#a1a1aa', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
                    {JSON.stringify(e, null, 2)}
                  </pre>
                )}
              </div>
            ))}
            {log.length === 0 && <div style={{ padding: '14px', fontSize: '12px', color: '#71717a' }}>No events yet.</div>}
          </div>
        </div>
      </div>
    </div>
  );
};
