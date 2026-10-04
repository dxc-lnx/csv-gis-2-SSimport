"""
Update distress quantities (columns 2-18) in Existing_predict_csv with values from
New_predict_csv by matching on agency, VideoName, and FrameNumber. Save to Updated_predict_csv.
"""
import re
import pandas as pd

Existing_predict_csv = r"input\Richmond_predicted_2026-01-13.csv"
New_predict_csv = r"input\Richmond_predict_summary_2026-02-14.csv"
Updated_predict_csv = r"input\Richmond_predict_DC_2026-02-14_updated.csv"
Agency_name = "Richmond"

# Distress columns (columns 2-18 in 1-based; indices 1-17 in 0-based)
DISTRESS_COLS = [
    "Alligator-H", "Alligator-L", "Alligator-M",
    "Block-H", "Block-L", "Block-M",
    "L-T-H", "L-T-L", "L-T-M",
    "Patch-H", "Patch-L", "Patch-M",
    "Ravel-H", "Ravel-M",
    "Weather-H", "Weather-L", "Weather-M",
]


def match_key_from_existing_path(image_name: str, agency: str) -> tuple:
    """
    From Existing CSV Image-Name like:
    outputimages/2025-10-24Richmond/1016202544255PMGX010280.MP4/.../processed_frames/res_st_td_frame_0.jpg
    return (agency, video_name, frame_number) e.g. ("Richmond", "1016202544255PMGX010280.MP4", "st_td_frame_0").
    """
    if not isinstance(image_name, str) or not image_name.strip():
        return ("", "", "")
    s = image_name.strip()
    # Get .mp4 filename (last path segment that ends with .mp4 before processed_frames)
    video_m = re.search(r"([^/\\]+\.mp4)", s, re.IGNORECASE)
    video_name = video_m.group(1) if video_m else ""
    # Frame: from res_*_frame_*.jpg take the base name without "res_" and ".jpg"
    frame_m = re.search(r"res_(.+)\.jpg\s*$", s, re.IGNORECASE)
    if frame_m:
        frame_number = frame_m.group(1).strip()
    else:
        frame_number = ""
    return (agency.strip(), video_name, frame_number)


def match_key_from_new_path(image_name: str) -> tuple:
    """
    From New CSV Image-Name like: 2025-10-24Richmond__1016202544255PMGX010280.MP4__st_td_frame_0
    return (agency, video_name, frame_number). Agency is parsed from the first segment (after date).
    """
    if not isinstance(image_name, str) or not image_name.strip():
        return ("", "", "")
    parts = image_name.strip().split("__")
    if len(parts) != 3:
        return ("", "", "")
    date_agency, video_name, frame_number = parts[0].strip(), parts[1].strip(), parts[2].strip()
    # Agency: strip leading YYYY-MM-DD or YYYY-M-D from date_agency
    agency_m = re.match(r"^\d{4}-\d{1,2}-\d{1,2}(.+)", date_agency)
    agency = agency_m.group(1) if agency_m else date_agency
    return (agency, video_name, frame_number)


def main():
    existing_df = pd.read_csv(Existing_predict_csv)
    new_df = pd.read_csv(New_predict_csv)
    # Normalize column names (strip spaces, e.g. "Image-Name                                       " -> "Image-Name")
    existing_df.columns = [c.strip() if isinstance(c, str) else c for c in existing_df.columns]
    new_df.columns = [c.strip() if isinstance(c, str) else c for c in new_df.columns]

    if "Image-Name" not in existing_df.columns:
        raise ValueError("Existing CSV must have an 'Image-Name' column.")
    if "Image-Name" not in new_df.columns:
        raise ValueError("New CSV must have an 'Image-Name' column.")

    # Use only distress columns that exist in both
    distress_in_both = [c for c in DISTRESS_COLS if c in existing_df.columns and c in new_df.columns]
    if not distress_in_both:
        raise ValueError("No matching distress columns found between Existing and New CSV.")
    missing_existing = [c for c in DISTRESS_COLS if c not in existing_df.columns]
    if missing_existing:
        print(f"Note: Existing CSV missing columns (will not be updated): {missing_existing}")

    # Build lookup from New: (agency, video_name, frame_number) -> row (distress values)
    new_lookup = {}
    for idx, row in new_df.iterrows():
        key = match_key_from_new_path(row["Image-Name"])
        if key[0] and key[1] and key[2]:
            new_lookup[key] = row[distress_in_both].copy()

    # Update Existing rows (use float for distress columns to allow decimals from New CSV)
    updated_df = existing_df.copy()
    for col in distress_in_both:
        updated_df[col] = pd.to_numeric(updated_df[col], errors="coerce").astype(float)
    matched = 0
    for idx, row in updated_df.iterrows():
        key = match_key_from_existing_path(row["Image-Name"], Agency_name)
        if key in new_lookup:
            new_row = new_lookup[key]
            for col in distress_in_both:
                updated_df.at[idx, col] = float(new_row[col]) if pd.notna(new_row[col]) else new_row[col]
            matched += 1

    updated_df.to_csv(Updated_predict_csv, index=False)
    print(f"Matched {matched} of {len(updated_df)} rows. Saved to {Updated_predict_csv}")


if __name__ == "__main__":
    main()
