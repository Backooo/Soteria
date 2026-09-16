import React, { useState, useRef, useEffect } from 'react';
import {
  Search,
  Wifi,
  Bell,
  Plus,
  Train,
  Truck,
  ChevronDown,
  X
} from 'lucide-react';
import { useFleet } from '../../context/FleetContext';

interface TopNavBarProps {
  activeTab: string;
  setActiveTab: (tab: string) => void;
  isMapOnlyMode: boolean;
  toggleMapOnlyMode: () => void;
}

export const TopNavBar: React.FC<TopNavBarProps> = ({
  activeTab,
  setActiveTab,
  isMapOnlyMode,
  toggleMapOnlyMode
}) => {
  const {
    assets,
    selectedAsset,
    selectAsset,
    focusOnAsset,
    openAddModal,
    incidents,
    isNotificationSidebarOpen,
    toggleNotificationSidebar
  } = useFleet();

  const [isDropdownOpen, setIsDropdownOpen] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const searchRef = useRef<HTMLDivElement>(null);

  // Close dropdown on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setIsDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  const navItems = [
    { id: 'live-map', label: 'Live Map' },
    { id: 'fleet', label: 'Fleet' },
    { id: 'routes', label: 'Routes' },
    { id: 'analytics', label: 'Analytics' },
    { id: 'maintenance', label: 'Maintenance' },
    { id: 'incidents', label: 'Incidents' },
  ];

  const handleNavClick = (id: string) => {
    setActiveTab(id);
    if (id === 'live-map') {
      toggleMapOnlyMode();
    }
  };

  const filteredAssets = assets.filter(asset =>
    asset.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    asset.type.toLowerCase().includes(searchQuery.toLowerCase()) ||
    (asset.statusText && asset.statusText.toLowerCase().includes(searchQuery.toLowerCase()))
  );

  return (
    <header className="top-navbar">
      {/* Brand: Only name "Soteria" without logo */}
      <div className="nav-left">
        <div
          className="brand-badge"
          title="Soteria Command"
          style={{ cursor: 'pointer', display: 'flex', alignItems: 'center' }}
          onClick={() => {
            if (isMapOnlyMode) toggleMapOnlyMode();
          }}
        >
          <span
            style={{
              fontFamily: 'var(--font-sans)',
              fontSize: '18px',
              fontWeight: 700,
              letterSpacing: '-0.02em',
              color: '#ffffff',
              textShadow: '0 2px 12px rgba(0,0,0,0.6)',
              paddingRight: '6px'
            }}
          >
            Soteria
          </span>
        </div>

        {/* Pill Navigation */}
        <nav className="nav-pills-list">
          {navItems.map((item) => (
            <button
              key={item.id}
              className={`glass-pill ${item.id === 'live-map' && isMapOnlyMode ? 'active' : activeTab === item.id ? 'active' : ''
                }`}
              onClick={() => handleNavClick(item.id)}
              title={item.id === 'live-map' ? (isMapOnlyMode ? 'Alle Panels wieder einblenden' : 'Nur Map anzeigen') : undefined}
            >
              {item.label}
              {item.id === 'live-map' && isMapOnlyMode && (
                <span style={{ fontSize: '9px', padding: '1px 5px', background: '#ffffff', color: '#000000', borderRadius: '4px', fontWeight: 700, marginLeft: '4px' }}>
                  ONLY
                </span>
              )}
            </button>
          ))}
        </nav>
      </div>

      {/* Right side controls */}
      <div className="nav-right">
        {/* Quick Add Asset Button (Same format as Fleet, Routes, etc.) */}
        <button
          className="glass-pill"
          onClick={() => openAddModal('train')}
          title="Neuen Zug oder LKW hinzufügen"
        >
          <Plus size={14} />
          <span>Einheit hinzufügen</span>
        </button>

        {/* Vehicle Search & Selector in Header */}
        <div className="search-container" ref={searchRef} style={{ position: 'relative' }}>
          {selectedAsset ? (
            /* Active Vehicle Selected Pill */
            <div
              className="glass-pill"
              onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                padding: '6px 12px 6px 14px',
                background: 'rgba(255, 255, 255, 0.12)',
                border: '1px solid rgba(255, 255, 255, 0.3)',
                color: '#ffffff',
                cursor: 'pointer',
                borderRadius: 'var(--radius-pill)',
                minWidth: '180px',
                justifyContent: 'space-between',
                transition: 'all 0.2s ease',
              }}
              title="Klicken um anderes Fahrzeug zu wählen"
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '7px', minWidth: 0 }}>
                {selectedAsset.type === 'train' ? (
                  <Train size={15} color="#ffffff" />
                ) : (
                  <Truck size={15} color="var(--accent-emerald)" />
                )}
                <span style={{
                  fontWeight: 600,
                  fontSize: '13px',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  maxWidth: '160px'
                }}>
                  {selectedAsset.name.split(' ')[0]} {selectedAsset.name.split(' ')[1] || ''}
                </span>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    selectAsset(null);
                  }}
                  title="Auswahl aufheben (Search)"
                  style={{
                    background: 'rgba(255, 255, 255, 0.15)',
                    border: 'none',
                    borderRadius: '50%',
                    width: '18px',
                    height: '18px',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    cursor: 'pointer',
                    color: '#ffffff',
                    padding: 0
                  }}
                >
                  <X size={11} />
                </button>
                <ChevronDown
                  size={14}
                  color="var(--text-muted)"
                  style={{
                    transform: isDropdownOpen ? 'rotate(180deg)' : 'none',
                    transition: 'transform 0.2s ease'
                  }}
                />
              </div>
            </div>
          ) : (
            /* No Vehicle Selected: Clean input with placeholder "Search" */
            <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
              <input
                type="text"
                className="search-input"
                placeholder="Search"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setIsDropdownOpen(true);
                }}
                onFocus={() => setIsDropdownOpen(true)}
                style={{
                  paddingRight: '36px',
                  width: '200px'
                }}
              />
              <button
                className="search-icon-btn"
                aria-label="Suche"
                onClick={() => setIsDropdownOpen(!isDropdownOpen)}
              >
                <Search size={15} />
              </button>
            </div>
          )}

          {/* Vehicle Dropdown Menu */}
          {isDropdownOpen && (
            <div
              className="glass-panel"
              style={{
                position: 'absolute',
                top: 'calc(100% + 8px)',
                right: 0,
                width: '280px',
                maxHeight: '300px',
                overflowY: 'auto',
                padding: '6px',
                zIndex: 120,
                background: 'rgba(18, 18, 22, 0.96)',
                border: '1px solid rgba(255, 255, 255, 0.18)',
                boxShadow: '0 16px 40px rgba(0, 0, 0, 0.85), 0 0 0 1px rgba(255, 255, 255, 0.08) inset',
                borderRadius: '12px',
                animation: 'fadeIn 0.16s ease'
              }}
            >
              {/* Optional deselect row if asset is selected */}
              {selectedAsset && (
                <div
                  onClick={() => {
                    selectAsset(null);
                    setIsDropdownOpen(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '8px',
                    padding: '8px 12px',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    fontSize: '12px',
                    color: 'var(--text-muted)',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
                    marginBottom: '4px',
                    transition: 'background 0.15s ease'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(255, 255, 255, 0.06)'}
                  onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
                >
                  <X size={13} />
                  <span>Auswahl aufheben (Zurück zu "Search")</span>
                </div>
              )}

              {/* Assets list */}
              {filteredAssets.length === 0 ? (
                <div style={{ padding: '12px', textAlign: 'center', fontSize: '12px', color: 'var(--text-muted)' }}>
                  Keine Fahrzeuge gefunden
                </div>
              ) : (
                filteredAssets.map((asset) => {
                  const isCur = selectedAsset?.id === asset.id;
                  return (
                    <div
                      key={asset.id}
                      onClick={() => {
                        focusOnAsset(asset);
                        setIsDropdownOpen(false);
                        setSearchQuery('');
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: '10px',
                        padding: '8px 12px',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        fontSize: '13px',
                        color: isCur ? '#ffffff' : 'var(--text-secondary)',
                        background: isCur ? 'rgba(255, 255, 255, 0.14)' : 'transparent',
                        transition: 'background 0.15s ease',
                      }}
                      onMouseEnter={(e) => {
                        if (!isCur) e.currentTarget.style.background = 'rgba(255, 255, 255, 0.06)';
                      }}
                      onMouseLeave={(e) => {
                        if (!isCur) e.currentTarget.style.background = 'transparent';
                      }}
                    >
                      {asset.type === 'train' ? (
                        <Train size={15} color={isCur ? '#ffffff' : 'var(--text-muted)'} />
                      ) : (
                        <Truck size={15} color={asset.status === 'warning' ? 'var(--accent-amber)' : 'var(--accent-emerald)'} />
                      )}

                      <div style={{ display: 'flex', flexDirection: 'column', flex: 1, minWidth: 0 }}>
                        <span style={{
                          fontWeight: 600,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap'
                        }}>
                          {asset.name}
                        </span>
                        <span style={{ fontSize: '11px', color: 'var(--text-dim)', display: 'flex', gap: '6px' }}>
                          <span>{asset.speedKmh} km/h</span>
                          <span>•</span>
                          <span style={{ color: asset.status === 'warning' ? 'var(--accent-amber)' : 'var(--text-dim)' }}>
                            {asset.statusText}
                          </span>
                        </span>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          )}
        </div>

        {/* Action icons */}
        <div className="nav-action-icons">
          {/* WIFI / Latency Indicator: Green / Online with 1ms */}
          <div
            title="Latenz: 1 ms (IoT & Satellit Online)"
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '0 10px',
              height: '36px',
              borderRadius: '18px',
              color: 'var(--accent-emerald)',
              border: '1px solid rgba(16, 185, 129, 0.35)',
              background: 'rgba(16, 185, 129, 0.12)',
              boxShadow: '0 0 12px rgba(16, 185, 129, 0.2)',
              fontSize: '12px',
              fontWeight: 600,
              letterSpacing: '-0.01em',
              userSelect: 'none'
            }}
          >
            <Wifi size={15} />
            <span style={{ color: 'var(--accent-emerald)' }}>1ms</span>
          </div>

          {/* Bell Notifications: Opens/Closes the Apple-style Warning & Incidents Sidebar! */}
          <button
            className={`icon-button ${isNotificationSidebarOpen ? 'active-sim' : ''}`}
            onClick={toggleNotificationSidebar}
            title={isNotificationSidebarOpen ? 'Warnungen schließen' : 'Warnungen & Vorfälle öffnen'}
            style={isNotificationSidebarOpen ? { borderColor: 'var(--accent-rose)', color: 'var(--accent-rose)', background: 'rgba(239, 68, 68, 0.15)' } : {}}
          >
            <Bell size={16} />
            <span className="icon-badge">{incidents.length}</span>
          </button>
        </div>

        {/* Profile Avatar: ONLY PB with SS initials in frosted glass effect */}
        <div
          title="Benutzerprofil (SS)"
          style={{
            width: '36px',
            height: '36px',
            borderRadius: '50%',
            background: 'rgba(255, 255, 255, 0.08)',
            backdropFilter: 'blur(16px)',
            WebkitBackdropFilter: 'blur(16px)',
            border: '1px solid rgba(255, 255, 255, 0.2)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontSize: '12px',
            fontWeight: 700,
            color: '#ffffff',
            letterSpacing: '0.05em',
            boxShadow: '0 4px 14px rgba(0, 0, 0, 0.4), 0 0 0 1px rgba(255, 255, 255, 0.1) inset',
            cursor: 'pointer',
            transition: 'all 0.2s ease'
          }}
        >
          SS
        </div>
      </div>
    </header>
  );
};
