"""Lat/lon-style formatting for the compass HUD chip.

The map's scene units are already real meters (see scale_bar.py's "1 scene
unit == 1 meter" convention) — rather than inventing a fictional per-map
degree scale, this reuses the standard real-world equatorial conversion
(~111,320 m per degree) with the scene origin (0,0) as "0°N 0°L", the same
role Null Island plays in real-world lat/lon.
"""

METERS_PER_DEGREE = 111_320.0


def to_lat_lon(x_meters: float, y_meters: float) -> tuple[float, float]:
    # Scene Y grows downward (Qt convention); north is -Y, matching the
    # same flip main_layout.py already applies to the X/Y status bar readout.
    lat = -y_meters / METERS_PER_DEGREE
    lon = x_meters / METERS_PER_DEGREE
    return lat, lon


def format_lat_lon(lat: float, lon: float) -> str:
    return f"{abs(lat):.1f}°{'N' if lat >= 0 else 'S'} {abs(lon):.1f}°{'L' if lon >= 0 else 'O'}"
