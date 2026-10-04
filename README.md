# CSV to SSimport
Step 1: Prepare Layers
Make sure your points layer and polyline layer are both in a projected CRS (e.g., UTM).
(Distances in degrees don’t make sense.)

Step 2: Calculate the distances
Find the nearest neighbors (k) = 2

Step 3: Output
The output will be a table like the following:

| PointID | PolylineID | Distance |
| ------- | ---------- | -------- |
| P1      | L12        | 15.3     |
| P1      | L5         | 28.7     |
| P2      | L7         | 5.9      |
| P2      | L9         | 13.2     |

Step 4: Join the results back to the point layer:
We want the distances/IDs directly as attributes of the point layer:
Use Join attributes by field/value (or "Join by nearest") to attach the first result.
Repeat for the second-closest.
(Or pivot the table if you want both values in the same row.)
