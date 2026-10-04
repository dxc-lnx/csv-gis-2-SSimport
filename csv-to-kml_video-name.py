import csv
import os
from xml.sax.saxutils import escape

# --- CONFIGURE THESE ---
input_csv = "input\\Richmond_predict_DC_2025-12-15.csv"
output_kml = "input\\Richmond_predict_DC_2025-12-15.kml"

lat_col = "Latitude"
lon_col = "Longitude"
image_col = "Image-Name"   # full path we will parse to get video name
# ------------------------


def extract_video_name(image_path: str):
    """Extract the first component ending in .MP4 from the path."""
    parts = image_path.replace("\\", "/").split("/")
    for p in parts:
        if p.upper().endswith(".MP4"):
            return p
    return None


def csv_to_kml(input_csv, output_kml, lat_col, lon_col, image_col):
    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        kml_parts = []
        kml_parts.append(
            """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>Points from CSV</name>
"""
        )

        seen_videos = set()

        for i, row in enumerate(reader, start=1):
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except:
                continue

            # Extract video name from the Image-Name path
            img_path = row.get(image_col, "")
            video_name = extract_video_name(img_path)

            # Default empty name
            name = ""

            if video_name:
                if video_name not in seen_videos:
                    name = video_name  # label the first point of this video
                    seen_videos.add(video_name)

            coord_str = f"{lon},{lat},0"

            placemark = f"""  <Placemark>
    <name>{escape(name)}</name>
    <Point>
      <coordinates>{coord_str}</coordinates>
    </Point>
  </Placemark>
"""
            kml_parts.append(placemark)

        kml_parts.append("</Document>\n</kml>\n")

    with open(output_kml, "w", encoding="utf-8") as out_f:
        out_f.writelines(kml_parts)


if __name__ == "__main__":
    csv_to_kml(input_csv, output_kml, lat_col, lon_col, image_col)
    print(f"Written KML to: {output_kml}")
