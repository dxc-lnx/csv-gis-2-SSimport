import csv
from xml.sax.saxutils import escape

# --- CONFIGURE THESE ---
input_csv = "input\\Richmond_predict_DC_2025-12-15.csv"
output_kml = "input\\Richmond_predict_DC_2025-12-15.kml"

lat_col = "Latitude"
lon_col = "Longitude"
name_col = None  # or None if you don't want names
# ------------------------


def csv_to_kml(input_csv, output_kml, lat_col, lon_col, name_col=None):
    with open(input_csv, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)

        kml_parts = []
        # KML header
        kml_parts.append(
            """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2">
<Document>
  <name>Points from CSV</name>
"""
        )

        for i, row in enumerate(reader, start=1):
            try:
                lat = float(row[lat_col])
                lon = float(row[lon_col])
            except (KeyError, ValueError):
                # Skip rows with missing or invalid coordinates
                continue
            name=""

            # KML wants lon,lat,alt
            coord_str = f"{lon},{lat},0"

            placemark = f"""  <Placemark>
    <name>{escape(name)}</name>
    <Point>
      <coordinates>{coord_str}</coordinates>
    </Point>
  </Placemark>
"""
            kml_parts.append(placemark)

        # KML footer
        kml_parts.append("</Document>\n</kml>\n")

    # Write out the KML
    with open(output_kml, "w", encoding="utf-8") as out_f:
        out_f.writelines(kml_parts)


if __name__ == "__main__":
    csv_to_kml(input_csv, output_kml, lat_col, lon_col, name_col)
    print(f"Written KML to: {output_kml}")
