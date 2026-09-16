import React from 'react';
import { ScheduleOffsetTable } from '../metrics/ScheduleOffsetTable';
import { LiveVolumeChart } from '../metrics/LiveVolumeChart';

export const BottomMetricsPanel: React.FC = () => {
  return (
    <section className="bottom-metrics-panel">
      {/* Schedule Offset Table (± 2.5 min Average Variance) */}
      <ScheduleOffsetTable />

      {/* Affected Wagons Chart (real wagon/incident data) */}
      <LiveVolumeChart />
    </section>
  );
};
