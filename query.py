import os
import sys
import datetime as dt

import pandas as pd
from qgis.core import QgsApplication, QgsProject

DEFAULT_INPUT_CSV = os.path.join(os.getcwd(), "input", "path_data.csv")
PROJECT_PATH = r"shortest-dist-gis-map.qgz"
ERROR_LAYER_NAME = "Error" 
REMOVED_LOG_CSV = os.path.join(os.getcwd(), "input", "removed_by_error_layer.csv")

# -----------------------------
# Initialize QGIS
# -----------------------------
qgs = QgsApplication([], False)
qgs.initQgis()

try:
    # -----------------------------
    # Load project
    # -----------------------------
    if not os.path.exists(PROJECT_PATH):
        raise FileNotFoundError(f"Project not found: {PROJECT_PATH}")
    QgsProject.instance().read(PROJECT_PATH)

    # -----------------------------
    # Get 'Error' layer and its PointIDs
    # -----------------------------
    layers = QgsProject.instance().mapLayersByName(ERROR_LAYER_NAME)
    if not layers:
        raise RuntimeError(f"Layer '{ERROR_LAYER_NAME}' not found in project.")
    error_lyr = layers[0]

    if "PointID" not in [f.name() for f in error_lyr.fields()]:
        raise RuntimeError("Field 'PointID' not found in the 'Error' layer.")

    point_ids = set()
    for f in error_lyr.getFeatures():
        val = f["PointID"]
        if val is not None and str(val).strip() != "":
            point_ids.add(str(val))

    print(f"Collected PointIDs from '{ERROR_LAYER_NAME}': {len(point_ids)}")

    # -----------------------------
    # Read input CSV
    # -----------------------------
    input_csv = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT_CSV
    if not os.path.exists(input_csv):
        raise FileNotFoundError(f"Input CSV not found: {input_csv}")

    df = pd.read_csv(input_csv)
    if "Image-Name" not in df.columns:
        raise RuntimeError("Column 'Image-Name' not found in input CSV.")

    # Normalize to string for matching
    df["Image-Name"] = df["Image-Name"].astype(str)

    # -----------------------------
    # Build masks and split
    # -----------------------------
    to_remove_mask = df["Image-Name"].isin(point_ids)
    removed_df = df[to_remove_mask].copy()
    kept_df = df[~to_remove_mask].copy()

    print(f"Rows in input: {len(df)}")
    print(f"Rows matching PointID (to remove): {len(removed_df)}")
    print(f"Rows kept: {len(kept_df)}")

    # -----------------------------
    # Backup original, overwrite input with kept rows, log removed
    # -----------------------------
    # Ensure output folder exists (for removed log)
    os.makedirs(os.path.dirname(REMOVED_LOG_CSV), exist_ok=True)

    ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    base, ext = os.path.splitext(input_csv)
    backup_csv = f"{base}.bak_{ts}{ext}"

    # Backup original
    df.to_csv(backup_csv, index=False)
    print(f"Backup written: {backup_csv}")

    # Overwrite input with kept rows
    kept_df.to_csv(input_csv, index=False)
    print(f"Filtered CSV written (overwrote input): {input_csv}")

    # Save removed rows for audit
    removed_df.to_csv(REMOVED_LOG_CSV, index=False)
    print(f"Removed rows written: {REMOVED_LOG_CSV}")

finally:
    # -----------------------------
    # Cleanup QGIS
    # -----------------------------
    qgs.exitQgis()
