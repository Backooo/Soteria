import React, { useState } from 'react';
import { ArrowUpRight } from 'lucide-react';

export const EfficiencySparkline: React.FC = () => {
  const [hoveredPoint, setHoveredPoint] = useState<{ time: string; val: number } | null>(null);

  const dataPoints = [
    { time: '06:00', val: 54 },
    { time: '07:30', val: 62 },
    { time: '09:00', val: 78 },
    { time: '10:30', val: 74 },
    { time: '12:00', val: 86 },
    { time: '13:30', val: 79 },
    { time: '15:00', val: 68 },
    { time: '16:30', val: 72 },
    { time: '18:00', val: 88 },
    { time: '19:30', val: 81 },
    { time: '21:00', val: 78.3 },
  ];

  // SVG Chart Dimensions
  const width = 390;
  const height = 75;
  const paddingX = 10;
  const paddingY = 8;

  const minVal = 20;
  const maxVal = 100;

  const points = dataPoints.map((pt, idx) => {
    const x = paddingX + (idx / (dataPoints.length - 1)) * (width - paddingX * 2);
    const y = height - paddingY - ((pt.val - minVal) / (maxVal - minVal)) * (height - paddingY * 2);
    return { ...pt, x, y };
  });

  const pathD = points.reduce((acc, curr, idx) => {
    if (idx === 0) return `M ${curr.x} ${curr.y}`;
    const prev = points[idx - 1];
    const cp1x = prev.x + (curr.x - prev.x) / 2;
    const cp1y = prev.y;
    const cp2x = prev.x + (curr.x - prev.x) / 2;
    const cp2y = curr.y;
    return `${acc} C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${curr.x} ${curr.y}`;
  }, '');

  const areaD = `${pathD} L ${points[points.length - 1].x} ${height} L ${points[0].x} ${height} Z`;

  return (
    <div className="glass-card" style={{ padding: '12px 14px' }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
        <span style={{ fontSize: '13px', fontWeight: 500, color: 'var(--text-secondary)' }}>
          Operational Efficiency
        </span>
        <span className="card-header-icon">
          <ArrowUpRight size={15} />
        </span>
      </div>

      {/* Main Metric */}
      <div style={{ display: 'flex', alignItems: 'baseline', gap: '4px', marginBottom: '2px' }}>
        <span style={{ fontSize: '32px', fontWeight: 600, letterSpacing: '-0.03em', color: '#ffffff' }}>
          78.3
        </span>
        <span style={{ fontSize: '16px', fontWeight: 400, color: 'var(--text-muted)' }}>
          %
        </span>
      </div>

      {/* Target Subtitle */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-muted)', marginBottom: '6px' }}>
        <span>Target:</span>
        <span style={{ color: '#ffffff', fontSize: '11px', fontWeight: 600 }}>
          {hoveredPoint ? `${hoveredPoint.time}: ${hoveredPoint.val}%` : '>80%'}
        </span>
      </div>

      {/* Interactive SVG Sparkline */}
      <div style={{ position: 'relative', width: '100%', height: `${height}px` }}>
        <svg 
          width="100%" 
          height="100%" 
          viewBox={`0 0 ${width} ${height}`} 
          preserveAspectRatio="none"
          style={{ overflow: 'visible' }}
        >
          <defs>
            <linearGradient id="efficiencyGradient" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0.2" />
              <stop offset="100%" stopColor="#ffffff" stopOpacity="0.0" />
            </linearGradient>
          </defs>

          {/* Target Reference Line (80%) */}
          <line
            x1={paddingX}
            y1={height - paddingY - ((80 - minVal) / (maxVal - minVal)) * (height - paddingY * 2)}
            x2={width - paddingX}
            y2={height - paddingY - ((80 - minVal) / (maxVal - minVal)) * (height - paddingY * 2)}
            stroke="rgba(255, 255, 255, 0.12)"
            strokeDasharray="4,4"
            strokeWidth="1"
          />

          {/* Filled Area */}
          <path d={areaD} fill="url(#efficiencyGradient)" />

          {/* Sparkline Curve */}
          <path 
            d={pathD} 
            fill="none" 
            stroke="rgba(255, 255, 255, 0.75)" 
            strokeWidth="1.8" 
          />

          {/* Interactive Highlight Points */}
          {points.map((pt, idx) => (
            <g key={idx} onMouseEnter={() => setHoveredPoint(pt)} onMouseLeave={() => setHoveredPoint(null)}>
              {/* Invisible touch target */}
              <circle cx={pt.x} cy={pt.y} r="10" fill="transparent" style={{ cursor: 'pointer' }} />
              
              {/* Render key dots matching image */}
              {(idx === 2 || idx === 4 || idx === 8 || idx === points.length - 1) && (
                <>
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="4"
                    fill="#18181b"
                    stroke="#ffffff"
                    strokeWidth="2"
                  />
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="2"
                    fill="#ffffff"
                  />
                </>
              )}
            </g>
          ))}
        </svg>

        {/* Right axis labels */}
        <div style={{ position: 'absolute', right: 0, top: 0, bottom: 0, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: '9px', color: 'var(--text-dim)', pointerEvents: 'none' }}>
          <span>100%</span>
          <span>75%</span>
          <span>50%</span>
          <span>25%</span>
        </div>
      </div>

      {/* Time interval ticks underneath chart */}
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '10px', color: 'var(--text-dim)', marginTop: '6px' }}>
        <span>06:00</span>
        <span>09:00</span>
        <span>12:00</span>
        <span>15:00</span>
        <span>18:00</span>
        <span>21:00</span>
      </div>
    </div>
  );
};
