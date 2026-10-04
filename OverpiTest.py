import os
import time

import overpy
import geopandas as gpd

from shapely.geometry import LineString, MultiLineString, GeometryCollection
from shapely.ops import linemerge, unary_union, nearest_points

# Shapely 2.x provides substring() (used to slice a line between two measures).
# If you're on Shapely 1.8, substring may not exist.
try:
    from shapely.ops import substring
except Exception:
    substring = None

from overpy.exception import OverpassGatewayTimeout, OverpassTooManyRequests, OverpassBadRequest


# =============================================================================
# Static input row (single test case)
# =============================================================================
# This represents one row from your CSV:
# - The road we are "surveying" is Orion Street
# - The start point is 270 ft North of West Tower Avenue
# - The end point is 70 ft North of West Tower Avenue
ROW = {
    "surveyed_street": "Orion Street",
    "beginning_street": "Stardust Place",
    "end_street": "West Tower Avenue",

    "start_direction": "N",
    "start_feet": 270.0,
    "start_comment_street": "West Tower Avenue",

    "end_direction": "N",
    "end_feet": 70.0,
    "end_comment_street": "West Tower Avenue",
}

# Overpass bbox restriction (south, west, north, east).
# This limits the data pulled from OpenStreetMap.
BBOX_S = 37.4539161
BBOX_W = -122.3738200
BBOX_N = 37.9066896
BBOX_E = -121.4690903

# Output files (written relative to the working directory you run the script from).
# These shapefiles can be loaded into QGIS to validate results.
OUT_LINE_SHP = r"test\orion_segment.shp"
OUT_PTS_SHP  = r"test\orion_debug_points.shp"


# =============================================================================
# Overpass helpers
# =============================================================================
api = overpy.Overpass()

def build_query(street_name: str, timeout_seconds: int = 180) -> str:
    """
    Build an Overpass XML query to fetch OSM 'ways' (roads) with:
      - highway=*  (road features)
      - name=<street_name>
    and exclude common non-road highway types.
    The bbox-query restricts to the provided bounding box.
    """
    return f"""
<osm-script output="json" timeout="{timeout_seconds}">
  <query type="way">
    <has-kv k="highway"/>
    <has-kv k="name" v="{street_name}"/>

    <has-kv k="highway" modv="not" v="footway"/>
    <has-kv k="highway" modv="not" v="pedestrian"/>
    <has-kv k="highway" modv="not" v="path"/>
    <has-kv k="highway" modv="not" v="service"/>
    <has-kv k="highway" modv="not" v="driveway"/>

    <bbox-query s="{BBOX_S}" w="{BBOX_W}" n="{BBOX_N}" e="{BBOX_E}"/>
  </query>

  <print mode="body"/>
  <recurse type="down"/>
  <print mode="skeleton"/>
</osm-script>
""".strip()

def query_with_retries(query: str, max_attempts: int = 6, base_sleep: float = 2.0):
    """
    Run an Overpass query with retry + exponential backoff.

    Overpass can return "server load too high" (timeouts / too many requests).
    We retry those cases, sleeping 2s, 4s, 8s, ... between attempts.

    If the query is malformed (BadRequest), we raise immediately.
    """
    last_err = None

    for attempt in range(1, max_attempts + 1):
        try:
            return api.query(query)

        except (OverpassGatewayTimeout, OverpassTooManyRequests) as e:
            last_err = e
            sleep_s = base_sleep * (2 ** (attempt - 1))
            print(f"[Overpass busy] attempt {attempt}/{max_attempts} -> sleeping {sleep_s:.1f}s")
            time.sleep(sleep_s)

        except OverpassBadRequest:
            # XML / query syntax issue; retries won't help
            raise

    # If we ran out of attempts, raise the last "busy" exception
    raise last_err

def ways_to_geom(result: overpy.Result):
    """
    Convert Overpass returned 'ways' to Shapely geometries.

    - Each way becomes a LineString of (lon, lat) nodes.
    - We then union them together into one geometry.
    - linemerge() tries to connect touching segments.

    The result may be:
      - LineString (best case)
      - MultiLineString (common when the street is in multiple segments)
      - GeometryCollection (sometimes occurs after union/merge)
    """
    lines = []

    for way in result.ways:
        coords = [
            (float(n.lon), float(n.lat))
            for n in way.nodes
            if n.lon is not None and n.lat is not None
        ]

        # Need at least 2 points to form a line
        if len(coords) >= 2:
            lines.append(LineString(coords))

    if not lines:
        return None

    # Combine all returned street segments into one geometry object
    merged = unary_union(lines)

    # Attempt to merge connected segments into longer continuous lines
    try:
        merged = linemerge(merged)
    except Exception:
        # If merge fails, we keep the union result as-is
        pass

    return merged


# =============================================================================
# Geometry helpers
# =============================================================================
def ensure_substring_available():
    """
    substring() is used to slice a line between two distances along the line.
    This is required for extracting the surveyed segment.
    """
    if substring is None:
        raise RuntimeError(
            "This script needs shapely.ops.substring (Shapely 2.x). "
            "Upgrade shapely to 2.x if needed."
        )

def choose_offset_sign_by_direction(line: LineString, m_at: float, direction: str, step_m: float = 5.0) -> int:
    """
    Determine whether to move forward (+) or backward (-) along a line to match
    a compass direction N/S/E/W.

    Why needed:
      - OSM ways can be digitized in either direction
      - "North" might correspond to increasing measure or decreasing measure

    We test a small step forward/backward from m_at and choose the one that moves
    most in the requested direction.
    """
    # Candidate measures along the line (clamped within [0, line.length])
    m1 = max(0.0, m_at - step_m)
    m2 = min(line.length, m_at + step_m)

    # Points at current measure and slightly backward/forward
    p_at = line.interpolate(m_at)
    p_back = line.interpolate(m1)
    p_fwd  = line.interpolate(m2)

    # Vectors from current point to the candidates
    vb = (p_back.x - p_at.x, p_back.y - p_at.y)
    vf = (p_fwd.x  - p_at.x, p_fwd.y  - p_at.y)

    # Score a vector by how much it moves in the requested compass direction
    def score(vec):
        x, y = vec
        if direction == "N":
            return y      # more +Y is more north
        if direction == "S":
            return -y     # more -Y is more south
        if direction == "E":
            return x      # more +X is more east
        if direction == "W":
            return -x     # more -X is more west
        return 0.0

    # If forward movement matches the desired direction better, return +1 else -1
    return +1 if score(vf) >= score(vb) else -1

def _flatten_lines(geom):
    """
    Extract all LineString objects from any geometry type.

    This is important because Overpass streets often come back as:
      - MultiLineString (street broken into segments)
      - GeometryCollection (mixed geometry pieces)
    """
    if geom is None:
        return []

    if isinstance(geom, LineString):
        return [geom]

    if isinstance(geom, MultiLineString):
        return list(geom.geoms)

    if isinstance(geom, GeometryCollection):
        out = []
        for g in geom.geoms:
            out.extend(_flatten_lines(g))
        return out

    # If some other type appears, ignore it
    return []

def force_linestring(geom, reference_point):
    """
    substring() can only slice a single LineString, not a MultiLineString.

    Strategy:
      - Extract all LineStrings from geom
      - Choose the LineString closest to a reference_point

    reference_point is usually the "anchor" (closest point between surveyed street
    and the comment street), so this picks the most relevant street segment.
    """
    lines = _flatten_lines(geom)
    if not lines:
        raise RuntimeError(
            f"Could not extract LineStrings from geometry type: {getattr(geom, 'geom_type', type(geom))}"
        )

    # Choose the candidate line closest to the anchor
    best = min(lines, key=lambda ls: ls.distance(reference_point))
    return best


# =============================================================================
# Main process (static case)
# =============================================================================
def main():
    ensure_substring_available()

    # Ensure output folders exist so shapefile writing doesn't fail
    os.makedirs(os.path.dirname(OUT_LINE_SHP), exist_ok=True)
    os.makedirs(os.path.dirname(OUT_PTS_SHP), exist_ok=True)

    surveyed = ROW["surveyed_street"]
    start_comment = ROW["start_comment_street"]
    end_comment   = ROW["end_comment_street"]

    # 1) Download surveyed street geometry
    print(f"Querying surveyed street: {surveyed}")
    time.sleep(1.0)  # polite delay (reduces throttling)
    res_surveyed = query_with_retries(build_query(surveyed))

    # 2) Download comment street geometry for start/end anchor
    print(f"Querying start comment street: {start_comment}")
    time.sleep(1.0)
    res_start_c = query_with_retries(build_query(start_comment))

    # If start and end comment streets are the same, reuse the same result
    res_end_c = res_start_c if end_comment == start_comment else query_with_retries(build_query(end_comment))

    # 3) Convert Overpass results to geometries
    surveyed_geom_ll = ways_to_geom(res_surveyed) # Surveyed Street
    start_c_geom_ll  = ways_to_geom(res_start_c)  # Start Comment Street
    end_c_geom_ll    = ways_to_geom(res_end_c)    # End Comment Street

    if surveyed_geom_ll is None:
        raise RuntimeError(f"No geometry returned for surveyed street: {surveyed}")
    if start_c_geom_ll is None:
        raise RuntimeError(f"No geometry returned for comment street: {start_comment}")
    if end_c_geom_ll is None:
        raise RuntimeError(f"No geometry returned for comment street: {end_comment}")

    # 4) Project to a meter-based CRS (UTM 10N) so "feet" offsets are meaningful
    #    EPSG:4326 is degrees; EPSG:32610 is meters
    gdf_tmp = gpd.GeoDataFrame(
        {"name": ["surveyed", "start_c", "end_c"]},
        geometry=[surveyed_geom_ll, start_c_geom_ll, end_c_geom_ll],
        crs="EPSG:4326"
    ).to_crs("EPSG:32610")

    surveyed_geom = gdf_tmp.geometry.iloc[0] # Surveyed Street
    start_c_geom  = gdf_tmp.geometry.iloc[1] # Start Comment Street
    end_c_geom    = gdf_tmp.geometry.iloc[2] # End Comment Street

    # 5) Compute anchor points:
    #    These are points on the surveyed street closest to the comment street.
    anchor_start = nearest_points(surveyed_geom, start_c_geom)[0]
    anchor_end   = nearest_points(surveyed_geom, end_c_geom)[0]

    # 6) Ensure we have exactly one LineString to slice
    #    If multiple street segments exist, pick the one closest to the anchor.
    surveyed_line = force_linestring(surveyed_geom, anchor_start)

    # Recompute the anchors against the chosen line so measures/project are consistent
    surveyed_to_start = nearest_points(surveyed_line, start_c_geom)[0]
    surveyed_to_end   = nearest_points(surveyed_line, end_c_geom)[0]

    print(f"Surveyed geometry type before force: {surveyed_geom.geom_type}")
    print(f"Surveyed geometry type after  force: {surveyed_line.geom_type}")

    # 7) Convert anchor points into measures (distance along the line, in meters)
    m_start_int = surveyed_line.project(surveyed_to_start)
    m_end_int   = surveyed_line.project(surveyed_to_end)

    # 8) Convert feet -> meters for the offsets
    start_offset_m = ROW["start_feet"] * 0.3048
    end_offset_m   = ROW["end_feet"] * 0.3048

    # 9) Decide whether offset is forward or backward along the line for N/S/E/W
    start_sign = choose_offset_sign_by_direction(surveyed_line, m_start_int, ROW["start_direction"])
    end_sign   = choose_offset_sign_by_direction(surveyed_line, m_end_int, ROW["end_direction"])

    # 10) Final measures for start/end points
    m_start = m_start_int + start_sign * start_offset_m
    m_end   = m_end_int   + end_sign   * end_offset_m

    # Clamp measures to the line length (stay within valid range)
    m_start = max(0.0, min(surveyed_line.length, m_start))
    m_end   = max(0.0, min(surveyed_line.length, m_end))

    # 11) Slice the surveyed road line between start and end measures
    m_a = min(m_start, m_end)
    m_b = max(m_start, m_end)
    segment = substring(surveyed_line, m_a, m_b)

    # 12) Output: Segment shapefile (polyline)
    out_line = gpd.GeoDataFrame(
        [{
            "surveyed": surveyed,
            "beg_str": ROW["beginning_street"],
            "end_str": ROW["end_street"],
            "s_dir": ROW["start_direction"],
            "s_ft": ROW["start_feet"],
            "s_cmt": ROW["start_comment_street"],
            "e_dir": ROW["end_direction"],
            "e_ft": ROW["end_feet"],
            "e_cmt": ROW["end_comment_street"],
        }],
        geometry=[segment],
        crs="EPSG:32610"   # currently in meters
    ).to_crs("EPSG:4326")  # write in WGS84 so QGIS loads easily

    # 13) Output: Debug points shapefile (helps verify correctness in QGIS)
    start_pt = surveyed_line.interpolate(m_start)  # computed start point
    end_pt   = surveyed_line.interpolate(m_end)    # computed end point

    out_pts = gpd.GeoDataFrame(
        [
            {"type": "start_intersection", "street": surveyed, "comment": start_comment},
            {"type": "end_intersection",   "street": surveyed, "comment": end_comment},
            {"type": "start_point",        "street": surveyed, "direction": ROW["start_direction"], "feet": ROW["start_feet"]},
            {"type": "end_point",          "street": surveyed, "direction": ROW["end_direction"],   "feet": ROW["end_feet"]},
        ],
        geometry=[surveyed_to_start, surveyed_to_end, start_pt, end_pt],
        crs="EPSG:32610"
    ).to_crs("EPSG:4326")

    # 14) Write files to disk
    out_line.to_file(OUT_LINE_SHP, driver="ESRI Shapefile")
    out_pts.to_file(OUT_PTS_SHP, driver="ESRI Shapefile")

    print("Done.")
    print(f"Segment shapefile: {OUT_LINE_SHP}")
    print(f"Debug points:      {OUT_PTS_SHP}")


if __name__ == "__main__":
    main()
