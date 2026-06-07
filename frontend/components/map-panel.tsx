"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { setOptions, importLibrary } from "@googlemaps/js-api-loader";

import type { MapResponse } from "@/lib/types";

const DAY_COLORS = [
  "#00ff41", // Default/Day 0 (Teal/Green)
  "#f1c40f", // Day 1 Amber
  "#e74c3c", // Day 2 Red
  "#9b59b6", // Day 3 Purple
  "#3498db", // Day 4 Blue
  "#e67e22", // Day 5 Orange
  "#1abc9c", // Day 6 Turquoise
];

// The loader touches `window`, so options must be set in the browser only — never at
// module top level, which also runs during server-side rendering (where `window` is
// undefined). Guarded so it runs exactly once on the client.
let optionsInitialized = false;
function ensureLoaderOptions() {
  if (optionsInitialized) return;
  setOptions({
    key: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "",
    v: "weekly",
    libraries: ["marker"],
  });
  optionsInitialized = true;
}

type Props = {
  map: MapResponse;
  selectedPlaceId?: string | null;
  onPlaceClick?: (id: string) => void;
  activeDay?: string | null;
  baseLat?: number;
  baseLng?: number;
};

export function MapPanel({ map, selectedPlaceId, onPlaceClick, activeDay, baseLat, baseLng }: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapInstanceRef = useRef<google.maps.Map | null>(null);
  
  // Storage for currently rendered objects to allow targeted updates
  const markersRef = useRef<Map<string, google.maps.marker.AdvancedMarkerElement>>(new Map());
  const pinsRef = useRef<Map<string, google.maps.marker.PinElement>>(new Map());
  const polylinesRef = useRef<google.maps.Polyline[]>([]);
  
  const [isMapLoaded, setIsMapLoaded] = useState(false);

  // We assign a color per date in the itinerary
  const dateColors = useMemo(() => {
    if (!map) return {};
    const dates = Array.from(new Set(map.markers.map(m => m.date).filter(Boolean))).sort() as string[];
    const mapColors: Record<string, string> = {};
    dates.forEach((d, i) => {
      mapColors[d] = DAY_COLORS[(i + 1) % DAY_COLORS.length];
    });
    return mapColors;
  }, [map]);

  // CAMERA EFFECT: Panning and centering logic
  useEffect(() => {
    const mapInstance = mapInstanceRef.current;
    if (!mapInstance || !isMapLoaded || !selectedPlaceId) return;

    const markerData = map.markers.find(m => m.id === selectedPlaceId);
    if (markerData) {
      mapInstance.panTo({ lat: markerData.lat, lng: markerData.lng });
      if (mapInstance.getZoom()! < 15) {
        mapInstance.setZoom(15);
      }
    }
  }, [selectedPlaceId, isMapLoaded, map.markers]);

  // STYLING EFFECT: Independent from map re-creation
  useEffect(() => {
    if (!isMapLoaded) return;

    // First, reset all markers back to their default "Day Color" and scale
    pinsRef.current.forEach((pin, id) => {
      const markerData = map.markers.find(m => m.id === id);
      if (!markerData) return;
      
      const isAccommodation = markerData.kind === "accommodation";
      const dayColor = markerData.date ? dateColors[markerData.date] || DAY_COLORS[0] : (isAccommodation ? "#f1c40f" : DAY_COLORS[0]);
      
      pin.scale = 1.0;
      pin.background = dayColor;
      
      const marker = markersRef.current.get(id);
      if (marker) marker.zIndex = 0;
    });

    // Then, if there is a selected ID, apply the high-visibility highlight
    if (selectedPlaceId) {
      const pin = pinsRef.current.get(selectedPlaceId);
      const marker = markersRef.current.get(selectedPlaceId);
      if (pin && marker) {
        pin.scale = 1.6;
        pin.background = "#ffffff";
        marker.zIndex = 1000;
      }
    }
  }, [selectedPlaceId, isMapLoaded, map.markers, dateColors]);

  // CORE RENDER EFFECT: Map initialization and marker creation
  useEffect(() => {
    if (!containerRef.current || !map) return;

    let disposed = false;

    const initMap = async () => {
      ensureLoaderOptions();
      const { Map } = (await importLibrary("maps")) as google.maps.MapsLibrary;
      const { AdvancedMarkerElement, PinElement } = (await importLibrary("marker")) as google.maps.MarkerLibrary;

      if (disposed) return;

      if (!mapInstanceRef.current) {
        const centerLat = map.markers.length > 0 ? map.markers[0].lat : (baseLat || 0);
        const centerLng = map.markers.length > 0 ? map.markers[0].lng : (baseLng || 0);
        
        mapInstanceRef.current = new Map(containerRef.current!, {
          center: { lat: centerLat, lng: centerLng },
          zoom: map.markers.length > 0 ? 13 : 11,
          mapId: process.env.NEXT_PUBLIC_GOOGLE_MAPS_MAP_ID || "DEMO_MAP_ID",
          disableDefaultUI: true,
          zoomControl: true,
        });
      }

      const instance = mapInstanceRef.current;

      // 1. CLEAR OLD STATE
      markersRef.current.forEach(m => m.map = null);
      markersRef.current.clear();
      pinsRef.current.clear();
      polylinesRef.current.forEach(p => p.setMap(null));
      polylinesRef.current = [];

      const bounds = new google.maps.LatLngBounds();

      // 2. DRAW ROUTES
      const filteredRoutes = map.routes.filter(r => !activeDay || activeDay === "all" || map.markers.find(m => m.id === r.from_marker_id)?.date === activeDay);
      
      filteredRoutes.forEach(route => {
        if (!route.geometry?.coordinates) return;
        const fromMarker = map.markers.find(m => m.id === route.from_marker_id);
        const dayColor = fromMarker?.date ? dateColors[fromMarker.date] || DAY_COLORS[0] : DAY_COLORS[0];
        
        const path = route.geometry.coordinates.map(coord => ({ lat: coord[1], lng: coord[0] }));
        const polyline = new google.maps.Polyline({
          path,
          geodesic: true,
          strokeColor: dayColor,
          strokeOpacity: 0.8,
          strokeWeight: 4,
          map: instance,
        });
        polylinesRef.current.push(polyline);
        path.forEach(p => bounds.extend(p));
      });

      // 3. DRAW MARKERS (with initial selection status)
      const filteredMarkers = map.markers.filter(m => !activeDay || activeDay === "all" || m.date === activeDay || !m.date);

      filteredMarkers.forEach(marker => {
        bounds.extend({ lat: marker.lat, lng: marker.lng });
        
        const isAccommodation = marker.kind === "accommodation";
        const isSelected = marker.id === selectedPlaceId;
        const dayColor = marker.date ? dateColors[marker.date] || DAY_COLORS[0] : (isAccommodation ? "#f1c40f" : DAY_COLORS[0]);

        const pin = new PinElement({
          background: isSelected ? "#ffffff" : dayColor,
          borderColor: "#000000",
          glyphColor: "#000000",
          scale: isSelected ? 1.6 : 1.0,
        });

        // Add smooth transitions directly to the element
        if (pin.element) {
          pin.element.style.transition = "all 0.4s cubic-bezier(0.4, 0, 0.2, 1)";
        }

        if (marker.date) {
            const dayMarkers = map.markers.filter(m => m.date === marker.date);
            const index = dayMarkers.findIndex(m => m.id === marker.id) + 1;
            pin.glyph = `${index}`;
        } else if (isAccommodation) {
            pin.glyph = "🏠";
        }

        const advancedMarker = new AdvancedMarkerElement({
          map: instance,
          position: { lat: marker.lat, lng: marker.lng },
          title: marker.title,
          content: pin.element,
          zIndex: isSelected ? 1000 : 0,
        });

        if (onPlaceClick) {
          // Future-proof: use gmp-click if available, but native click still works for now
          advancedMarker.addListener("click", () => onPlaceClick(marker.id));
        }
        
        markersRef.current.set(marker.id, advancedMarker);
        pinsRef.current.set(marker.id, pin);
      });

      // 4. FINALIZE
      setIsMapLoaded(true);
      if (!selectedPlaceId && !bounds.isEmpty()) {
        instance.fitBounds(bounds, 60);
      }
    };

    initMap();

    return () => { disposed = true; };
  }, [map, activeDay, dateColors, onPlaceClick]); // Note: NOT listening to selectedPlaceId for re-creation

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%", borderRadius: "1rem", overflow: "hidden" }} />
  );
}
