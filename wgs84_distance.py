from geographiclib.geodesic import Geodesic


def wgs84_distance_feet(lat1, lon1, lat2, lon2):
    """
    High-precision geodesic distance using WGS84 ellipsoid.
    Returns distance in feet.
    """
    result = Geodesic.WGS84.Inverse(lat1, lon1, lat2, lon2)
    meters = result["s12"]
    feet = meters * 3.280839895013123
    return feet


if __name__ == "__main__":
    # Example usage
    lat1, lon1 = 39.7480076, -121.8349289  # Chico, CA
    lat2, lon2 = 39.7479664, -121.8349966  
    distance = wgs84_distance_feet(lat1, lon1, lat2, lon2)
    print(f"Distance between points in Chico, CA: {distance:.2f} feet")