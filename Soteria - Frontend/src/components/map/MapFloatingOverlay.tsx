import React from 'react';
import { FloatingAssetTooltip } from './FloatingAssetTooltip';

export const MapFloatingOverlay: React.FC<{ onOpenEdit?: () => void }> = ({ onOpenEdit }) => {

  return (
    <>
      {/* Floating Center Header Area */}
      <div className="map-center-header">
        <h1 className="map-title">
          Incident Command
        </h1>
      </div>

      {/* Floating Popover Tooltip for active vehicle */}
      <FloatingAssetTooltip onOpenEdit={onOpenEdit} />
    </>
  );
};
