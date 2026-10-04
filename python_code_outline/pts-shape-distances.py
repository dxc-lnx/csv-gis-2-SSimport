# pip install geopandas shapely rtree pyproj
import geopandas as gpd
import pandas as pd
import numpy as np
from shapely.strtree import STRtree

# --- CONFIG ---
points_path = r"/path/to/your_points.shp"
lines_path  = r"/path/to/your_lines.shp"
csv_out     = r"/path/to/output/nearest2.csv"
point_id_field = "id"   # adjust or set to None to use index
line_id_field  = "id"   # adjust or set to None to use index

def utm_epsg_from_lonlat(lon, lat):
    zone = int(np.floor((lon + 180) / 6) + 1)
    south = lat < 0
    return f"EPSG:{32700 + zone if south else 32600 + zone}"

# Load
pts = gpd.read_file(points_path)
lns = gpd.read_file(lines_path)
assert len(pts) and len(lns), "Empty layer(s)."

# Reproject to metric CRS if geographic
if pts.crs is None or lns.crs is None:
    raise ValueError("Both layers must have a CRS.")
if pts.crs.is_geographic or lns.crs.is_geographic:
    # Pick a UTM zone from the mean point location
    mean_geom = pts.unary_union.centroid
    mean_lon, mean_lat = (mean_geom.x, mean_geom.y) if pts.crs.is_geographic else \
                         gpd.GeoSeries([mean_geom], crs=pts.crs).to_crs("EPSG:4326").iloc[0].coords[0]
    target_epsg = utm_epsg_from_lonlat(mean_lon, mean_lat)
    pts = pts.to_crs(target_epsg)
    lns = lns.to_crs(target_epsg)

# Prepare IDs
if point_id_field not in pts.columns:
    pts["_PID_"] = np.arange(len(pts))
    point_id_field = "_PID_"
if line_id_field not in lns.columns:
    lns["_LID_"] = np.arange(len(lns))
    line_id_field = "_LID_"

# Spatial index
line_geoms = lns.geometry.values
tree = STRtree(line_geoms)
geom_to_id = {geom: lns.iloc[i][line_id_field] for i, geom in enumerate(line_geoms)}

rows = []
for _, p in pts.iterrows():
    pg = p.geometry
    # Get nearby candidates (k a bit larger than 2 for safety)
    candidates = tree.nearest(pg, 10)  # returns array of geometries
    # Compute true distances
    pairs = []
    for g in candidates:
        lid = geom_to_id[g]
        d = pg.distance(g)
        pairs.append((lid, d))
    # Take the top 2
    pairs.sort(key=lambda x: x[1])
    (lid1, d1), (lid2, d2) = (pairs + [(None, np.nan), (None, np.nan)])[:2]
    rows.append({
        "point_id": p[point_id_field],
        "nearest_line_1": lid1,
        "distance_1_m": float(d1) if d1 == d1 else None,
        "nearest_line_2": lid2,
        "distance_2_m": float(d2) if d2 == d2 else None
    })

out = pd.DataFrame(rows)
out.to_csv(csv_out, index=False)
print(f"Wrote: {csv_out}")
