import React from 'react';
import { ArrowUpRight, Clock } from 'lucide-react';
import { useFleet } from '../../context/FleetContext';

export const ScheduleOffsetTable: React.FC = () => {
  const { routes } = useFleet();

  return (
    <div className="glass-card" style={{ padding: '10px 14px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
          Schedule Offset
        </span>
        <span className="card-header-icon">
          <ArrowUpRight size={15} />
        </span>
      </div>

      {/* Main Metric Stat */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '6px', marginBottom: '6px' }}>
        <span style={{ fontSize: '24px', fontWeight: 600, color: '#ffffff', letterSpacing: '-0.02em' }}>
          ± 2.5 min
        </span>
        <span style={{ fontSize: '11px', color: 'var(--text-muted)' }}>
          Average Variance
        </span>
      </div>

      {/* Route Variance Table */}
      <div style={{ width: '100%', overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px', fontFamily: 'var(--font-mono)' }}>
          <thead>
            <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.08)', color: 'var(--text-dim)', textAlign: 'left' }}>
              <th style={{ paddingBottom: '4px', fontWeight: 500, fontFamily: 'var(--font-sans)', color: 'var(--text-muted)' }}>Route number</th>
              <th style={{ paddingBottom: '4px', textAlign: 'center', fontWeight: 500 }}>L1</th>
              <th style={{ paddingBottom: '4px', textAlign: 'center', fontWeight: 500 }}>L12</th>
              <th style={{ paddingBottom: '4px', textAlign: 'center', fontWeight: 500 }}>L14</th>
              <th style={{ paddingBottom: '4px', textAlign: 'center', fontWeight: 500 }}>L15</th>
              <th style={{ paddingBottom: '4px', textAlign: 'center', fontWeight: 500 }}>L24</th>
            </tr>
          </thead>
          <tbody>
            {/* Row 1: L 45623 */}
            <tr style={{ borderBottom: '1px solid rgba(255, 255, 255, 0.04)' }}>
              <td style={{ padding: '4px 0', color: 'var(--text-secondary)' }}>
                <span style={{ padding: '1px 5px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', fontSize: '10px' }}>L</span> 45623
              </td>
              <td style={{ padding: '4px 0', textAlign: 'center', color: 'var(--text-muted)' }}>-2min</td>
              <td style={{ padding: '4px 0', textAlign: 'center', color: 'var(--text-amber)' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
                  <Clock size={10} /> +1min
                </span>
              </td>
              <td style={{ padding: '4px 0', textAlign: 'center', color: 'var(--text-amber)' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
                  <Clock size={10} /> +1.5min
                </span>
              </td>
              <td style={{ padding: '4px 0', textAlign: 'center', color: 'var(--text-muted)' }}>-1min</td>
              <td style={{ padding: '8px 0', textAlign: 'center', color: 'var(--text-muted)' }}>-1min</td>
            </tr>

            {/* Row 2: L 34654 */}
            <tr>
              <td style={{ padding: '8px 0', color: 'var(--text-secondary)' }}>
                <span style={{ padding: '2px 6px', background: 'rgba(255,255,255,0.06)', borderRadius: '4px', fontSize: '10px' }}>L</span> 34654
              </td>
              <td style={{ padding: '8px 0', textAlign: 'center', color: 'var(--text-muted)' }}>-1min</td>
              <td style={{ padding: '8px 0', textAlign: 'center', color: 'var(--text-muted)' }}>-2min</td>
              <td style={{ padding: '8px 0', textAlign: 'center', color: 'var(--text-amber)' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
                  <Clock size={10} /> +2min
                </span>
              </td>
              <td style={{ padding: '8px 0', textAlign: 'center', color: 'var(--text-muted)' }}>-2.5min</td>
              <td style={{ padding: '8px 0', textAlign: 'center', color: 'var(--text-amber)' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '2px' }}>
                  <Clock size={10} /> +2min
                </span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  );
};
