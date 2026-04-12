"use client";

import { useEffect, useRef, useState, useMemo } from "react";
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
  const markersRef = useRef<google.maps.marker.AdvancedMarkerElement[]>([]);
  const polylinesRef = useRef<google.maps.Polyline[]>([]);

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

  useEffect(() => {
    if (!containerRef.current || !map) return;

    let disposed = false;

    const initMap = async () => {
      setOptions({
        key: process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY || "",
        v: "weekly",
        libraries: ["marker"],
      });
      
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

      // Clear old markers & lines
      markersRef.current.forEach(m => m.map = null);
      markersRef.current = [];
      polylinesRef.current.forEach(p => p.setMap(null));
      polylinesRef.current = [];

      const bounds = new google.maps.LatLngBounds();

      // Draw Routes
      const filteredRoutes = map.routes.filter(r => !activeDay || activeDay === "all" || map.markers.find(m => m.id === r.from_marker_id)?.date === activeDay);
      
      filteredRoutes.forEach(route => {
        if (!route.geometry?.coordinates) return;
        const fromMarker = map.markers.find(m => m.id === route.from_marker_id);
        const dayColor = fromMarker?.date ? dateColors[fromMarker.date] || DAY_COLORS[0] : DAY_COLORS[0];
        
        const path = route.geometry.coordinates.map(coord => ({ lat: coord[1], lng: coord[0] })); // GeoJSON is [lng, lat]
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

      // Draw Markers
      const filteredMarkers = map.markers.filter(m => !activeDay || activeDay === "all" || m.date === activeDay || !m.date); // Keep accommodation without date

      filteredMarkers.forEach(marker => {
        bounds.extend({ lat: marker.lat, lng: marker.lng });
        
        const isAccommodation = marker.kind === "accommodation";
        const dayColor = marker.date ? dateColors[marker.date] || DAY_COLORS[0] : (isAccommodation ? "#f1c40f" : DAY_COLORS[0]);

        const pinBackground = new PinElement({
          background: dayColor,
          borderColor: "#000",
          glyphColor: "#000",
        });

        // Add index glyph if part of a day plan
        if (marker.date) {
            const dayMarkers = map.markers.filter(m => m.date === marker.date);
            const index = dayMarkers.findIndex(m => m.id === marker.id) + 1;
            pinBackground.glyph = `${index}`;
        } else if (isAccommodation) {
            pinBackground.glyph = "🏠";
        }

        const advancedMarker = new AdvancedMarkerElement({
          map: instance,
          position: { lat: marker.lat, lng: marker.lng },
          title: marker.title,
          content: pinBackground.element,
        });

        if (onPlaceClick) {
          advancedMarker.addListener("click", () => onPlaceClick(marker.id));
        }
        
        markersRef.current.push(advancedMarker);
      });

      if (!bounds.isEmpty()) {
        instance.fitBounds(bounds, 60); // 60px padding
      }
    };

    initMap();

    return () => { disposed = true; };
  }, [map, activeDay, dateColors, onPlaceClick]);

  return (
    <div ref={containerRef} style={{ width: "100%", height: "100%", borderRadius: "1rem", overflow: "hidden" }} />
  );
}
