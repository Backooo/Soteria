import React, { useEffect, useRef, useState } from 'react';
import mapboxgl from 'mapbox-gl';
import {
  Plus,
  Minus,
  Compass,
  RotateCw,
  Maximize2,
  Train,
  Truck,
  Building2,
  AlertTriangle,
  ArrowUpRight
} from 'lucide-react';
import { useFleet } from '../../context/FleetContext';
import { FleetAsset } from '../../types/fleet';
import { INITIAL_MAP_CENTER, INITIAL_MAP_ZOOM, INITIAL_MAP_PITCH, INITIAL_MAP_BEARING } from '../../data/mockFleetData';

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_ACCESS_TOKEN;

// High-fidelity dark-graded satellite style with moody contrast
const DARK_SATELLITE_STYLE: mapboxgl.Style = {
  version: 8,
  sources: {
    'satellite-tiles': {
      type: 'raster',
      tiles: [
        'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
      ],
      tileSize: 256,
      attribution: '© Esri World Imagery / Soteria Geospatial',
    },
    'dark-overlay-tiles': {
      type: 'raster',
      tiles: [
        'https://a.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}@2x.png',
      ],
      tileSize: 256,
    },
  },
  layers: [
    {
      id: 'background',
      type: 'background',
      paint: {
        'background-color': '#080808',
      },
    },
    {
      id: 'satellite-base',
      type: 'raster',
      source: 'satellite-tiles',
      paint: {
        'raster-saturation': -0.45,
        'raster-contrast': 0.45,
        'raster-brightness-max': 0.78,
        'raster-brightness-min': 0.04,
        'raster-hue-rotate': -10,
      },
    },
    {
      id: 'labels-overlay',
      type: 'raster',
      source: 'dark-overlay-tiles',
      paint: {
        'raster-opacity': 0.65,
      },
    },
  ],
};

export const InteractiveMap3D: React.FC = () => {
  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const markersRef = useRef<{ [id: string]: mapboxgl.Marker }>({});

  const {
    assets,
    routes,
    selectedAsset,
    selectAsset,
    setHoveredAsset,
    focusedCoordinates,
    is3DMode,
    toggle3DMode
  } = useFleet();

  const [mapLoaded, setMapLoaded] = useState(false);
  const [mapBearing, setMapBearing] = useState(INITIAL_MAP_BEARING);

  // Initialize Mapbox Map
  useEffect(() => {
    if (!mapContainerRef.current) return;

    mapboxgl.accessToken = MAPBOX_TOKEN;

    const map = new mapboxgl.Map({
      container: mapContainerRef.current,
      style: DARK_SATELLITE_STYLE,
      center: INITIAL_MAP_CENTER,
      zoom: INITIAL_MAP_ZOOM,
      pitch: INITIAL_MAP_PITCH,
      bearing: INITIAL_MAP_BEARING,
      antialias: true,
      maxPitch: 85,
    });

    mapRef.current = map;

    map.on('load', () => {
      setMapLoaded(true);

      // Add 3D Terrain from public AWS Terrarium elevation tiles
      if (!map.getSource('terrain-source')) {
        map.addSource('terrain-source', {
          type: 'raster-dem',
          tiles: [
            'https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png'
          ],
          tileSize: 256,
          encoding: 'terrarium',
          maxzoom: 15,
        });

        // Activate 3D elevation
        map.setTerrain({ source: 'terrain-source', exaggeration: 2.2 });

        // Add Hillshade layer for dramatic mountain relief lighting
        map.addLayer({
          id: 'alpine-hillshade',
          type: 'hillshade',
          source: 'terrain-source',
          paint: {
            'hillshade-exaggeration': 0.8,
            'hillshade-shadow-color': '#000000',
            'hillshade-highlight-color': '#3f3f46',
            'hillshade-accent-color': '#18181b',
          },
        }, 'labels-overlay');

        // Add 3D Horizon Atmosphere & Fog Depth
        map.setFog({
          range: [-0.5, 12],
          color: '#0a0a0c',
          'horizon-blend': 0.15,
          'high-color': '#18181b',
          'space-color': '#050505',
          'star-intensity': 0.45,
        });
      }

      // Add Routes GeoJSON source & glowing layers
      routes.forEach(route => {
        const sourceId = `source-${route.id}`;
        if (!map.getSource(sourceId)) {
          map.addSource(sourceId, {
            type: 'geojson',
            data: {
              type: 'Feature',
              properties: {
                name: route.name,
                code: route.code,
                color: route.color,
              },
              geometry: {
                type: 'LineString',
                coordinates: route.coordinates,
              },
            },
          });

          // Outer ambient glow line
          map.addLayer({
            id: `glow-${route.id}`,
            type: 'line',
            source: sourceId,
            layout: {
              'line-join': 'round',
              'line-cap': 'round',
            },
            paint: {
              'line-color': route.color,
              'line-width': 10,
              'line-opacity': 0.35,
              'line-blur': 4,
            },
          });

          // Sharp animated-style dashed core line
          map.addLayer({
            id: `core-${route.id}`,
            type: 'line',
            source: sourceId,
            layout: {
              'line-join': 'round',
              'line-cap': 'round',
            },
            paint: {
              'line-color': '#ffffff',
              'line-width': 2.5,
              'line-opacity': 0.95,
              'line-dasharray': route.type === 'rail' ? [3, 2] : [6, 3],
            },
          });
        }
      });
    });

    map.on('rotate', () => {
      setMapBearing(Math.round(map.getBearing()));
    });

    // Deselect active vehicle when clicking empty map terrain per user request
    map.on('click', () => {
      selectAsset(null);
    });

    mapRef.current = map;

    return () => {
      map.remove();
    };
  }, []);

  // Update 3D camera pitch and terrain when toggled
  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;

    if (is3DMode) {
      if (map.getSource('terrain-source')) {
        map.setTerrain({ source: 'terrain-source', exaggeration: 2.2 });
      }
      map.easeTo({
        pitch: 68,
        duration: 1200,
      });
    } else {
      map.setTerrain(null);
      map.easeTo({
        pitch: 0,
        duration: 1200,
      });
    }
  }, [is3DMode]);

  // Smooth camera flyTo when selectedAsset or focusedCoordinates changes
  useEffect(() => {
    if (!mapRef.current || !focusedCoordinates) return;
    mapRef.current.flyTo({
      center: focusedCoordinates,
      zoom: 13.5,
      pitch: is3DMode ? 68 : 0,
      speed: 1.2,
      curve: 1.4,
      essential: true,
    });
  }, [focusedCoordinates]);

  // Synchronize 3D Markers on Map
  useEffect(() => {
    if (!mapRef.current || !mapLoaded) return;
    const map = mapRef.current;

    // Track active IDs to clean up removed ones
    const activeIds = new Set<string>();

    assets.forEach((asset) => {
      activeIds.add(asset.id);
      const isSelected = selectedAsset?.id === asset.id;
      const isWarning = asset.status === 'warning';
      const isOffline = asset.status === 'offline';

      const pinColor = isOffline
        ? '#ef4444'
        : isWarning
          ? '#f59e0b'
          : asset.type === 'train'
            ? '#38bdf8'
            : asset.type === 'truck'
              ? '#10b981'
              : '#a855f7';

      if (markersRef.current[asset.id]) {
        // Update marker position
        markersRef.current[asset.id].setLngLat(asset.coordinates);

        // Update DOM element classes
        const el = markersRef.current[asset.id].getElement();
        el.className = `custom-map-marker ${isSelected ? 'is-selected' : ''}`;
      } else {
        // Create new DOM marker element
        const el = document.createElement('div');
        el.className = `custom-map-marker ${isSelected ? 'is-selected' : ''}`;
        el.style.width = '38px';
        el.style.height = '38px';
        el.style.display = 'flex';
        el.style.alignItems = 'center';
        el.style.justifyContent = 'center';

        // Outer dashed radar orbit for selected asset (as seen in reference screenshot)
        if (isSelected) {
          const orbit = document.createElement('div');
          orbit.style.position = 'absolute';
          orbit.style.width = '110px';
          orbit.style.height = '110px';
          orbit.style.borderRadius = '50%';
          orbit.style.border = '1.5px dashed rgba(255, 255, 255, 0.45)';
          orbit.style.pointerEvents = 'none';
          orbit.style.animation = 'spinOrbit 40s linear infinite';
          el.appendChild(orbit);
        }

        const inner = document.createElement('div');
        inner.className = 'marker-pin-inner';
        inner.style.backgroundColor = 'rgba(18, 18, 20, 0.92)';
        inner.style.borderColor = pinColor;
        inner.style.boxShadow = `0 0 18px ${pinColor}`;

        // Pulse ring
        const ring = document.createElement('div');
        ring.className = 'marker-pulse-ring';
        ring.style.border = `2px solid ${pinColor}`;
        inner.appendChild(ring);

        // Icon representation
        const iconSvg = document.createElement('div');
        iconSvg.style.display = 'flex';
        iconSvg.style.color = pinColor;
        iconSvg.innerHTML = asset.type === 'train'
          ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><rect width="16" height="16" x="4" y="3" rx="2"/><path d="M4 11h16"/><path d="M12 3v8"/><path d="m8 19-2 3"/><path d="m18 22-2-3"/><circle cx="8" cy="15" r="1"/><circle cx="16" cy="15" r="1"/></svg>`
          : asset.type === 'truck'
            ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 18V6a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2v11a1 1 0 0 0 1 1h2"/><path d="M15 18H9"/><path d="M19 18h2a1 1 0 0 0 1-1v-3.65a1 1 0 0 0-.22-.624l-3.48-4.35A1 1 0 0 0 17.52 8H14"/><circle cx="17" cy="18" r="2"/><circle cx="7" cy="18" r="2"/></svg>`
            : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M6 12H4a2 2 0 0 0-2 2v6a2 2 0 0 0 2 2h2"/><path d="M18 9h2a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-2"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/></svg>`;
        inner.appendChild(iconSvg);

        el.appendChild(inner);

        // Click handler to select asset
        el.addEventListener('click', (e) => {
          e.stopPropagation();
          selectAsset(asset);
        });

        // Hover handlers for sleek transparent popup on hover
        el.addEventListener('mouseenter', () => {
          setHoveredAsset(asset);
        });
        el.addEventListener('mouseleave', () => {
          setHoveredAsset(null);
        });

        const marker = new mapboxgl.Marker({ element: el, anchor: 'center' })
          .setLngLat(asset.coordinates)
          .addTo(map);

        markersRef.current[asset.id] = marker;
      }
    });

    // Remove orphaned markers
    Object.keys(markersRef.current).forEach((id) => {
      if (!activeIds.has(id)) {
        markersRef.current[id].remove();
        delete markersRef.current[id];
      }
    });
  }, [assets, selectedAsset, mapLoaded]);

  // Map Controls
  const rotationCountRef = useRef(0);

  const handleRotate90 = () => {
    if (!mapRef.current) return;
    rotationCountRef.current += 1;
    const targetBearing = INITIAL_MAP_BEARING + rotationCountRef.current * 90;
    mapRef.current.easeTo({
      bearing: targetBearing,
      duration: 650,
      easing: (t) => t * (2 - t),
    });
  };

  const handleZoomIn = () => mapRef.current?.zoomIn({ duration: 300 });
  const handleZoomOut = () => mapRef.current?.zoomOut({ duration: 300 });
  const handleResetNorth = () => mapRef.current?.resetNorthPitch({ duration: 500 });
  const handleFitCenter = () => {
    rotationCountRef.current = 0;
    mapRef.current?.flyTo({
      center: INITIAL_MAP_CENTER,
      zoom: INITIAL_MAP_ZOOM,
      pitch: is3DMode ? INITIAL_MAP_PITCH : 0,
      bearing: INITIAL_MAP_BEARING,
      duration: 1200,
    });
  };

  return (
    <div className="map-viewport">
      {/* Mapbox container */}
      <div ref={mapContainerRef} style={{ width: '100%', height: '100%' }} />

      {/* Floating Map Navigation Controls (bottom right: Kompass, 90° Rotate, +, -, 3D/2D) */}
      <div className="map-control-tools">
        <button
          className="map-tool-btn"
          onClick={handleFitCenter}
          title="Leitstand zentrieren"
        >
          <Compass size={18} />
        </button>
        <button
          className="map-tool-btn"
          onClick={handleRotate90}
          title="Perspektive um 90° drehen (nach 4 Klicks wieder Ursprung)"
        >
          <RotateCw size={16} />
        </button>
        <button
          className="map-tool-btn"
          onClick={handleZoomIn}
          title="Zoom In"
        >
          <Plus size={18} />
        </button>
        <button
          className="map-tool-btn"
          onClick={handleZoomOut}
          title="Zoom Out"
        >
          <Minus size={18} />
        </button>
        <button
          className="map-tool-btn"
          onClick={toggle3DMode}
          title={is3DMode ? 'In 2D Modus wechseln' : 'In 3D Modus wechseln'}
          style={{ fontWeight: 700, fontSize: '11px' }}
        >
          {is3DMode ? '3D' : '2D'}
        </button>
      </div>
    </div>
  );
};
