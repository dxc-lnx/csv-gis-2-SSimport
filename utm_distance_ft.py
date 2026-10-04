import math
import pyproj
from shapely.geometry import Point

def utm_epsg(lat, lon):

    zone = int((lon + 180) / 6) + 1
    hemisphere = 32600 if lat >= 0 else 32700  # 326XX = north, 327XX = south
    return hemisphere + zone

def utm_distance_m(lat1, lon1, lat2, lon2):

    epsg = utm_epsg(lat1, lon1)
    proj = pyproj.CRS.from_epsg(epsg)
    transformer = pyproj.Transformer.from_crs("EPSG:4326", proj, always_xy=True)

    x1, y1 = transformer.transform(lon1, lat1)
    x2, y2 = transformer.transform(lon2, lat2)

    return math.dist((x1, y1), (x2, y2))

def utm_distance_ft(lat1, lon1, lat2, lon2):
    meters = utm_distance_m(lat1, lon1, lat2, lon2)
    feet = meters * 3.280839895013123
    return feet

if __name__ == "__main__":
    # Example usage
    lat1, lon1 = 37.94396488333044, -122.335573

    lat2, lon2 = 37.94448049996995, -122.3355047


    distance = utm_distance_ft(lat1, lon1, lat2, lon2)
    print(f"UTM Distance between points in Chico, CA: {distance:.2f} feet")