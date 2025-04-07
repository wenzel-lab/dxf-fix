import math
import argparse
import ezdxf
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
import numpy as np
from collections import defaultdict, deque

# ==== CONFIGURATION ====
DEFAULT_UNIT = "mm"
DEFAULT_PRECISION_UM = 0.1
DEFAULT_ARC_SEGMENTS = 100
# ========================

UNIT_CONVERSION = {
    "mm": 1.0,
    "um": 0.001,
}

def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def flatten_arc(center, radius, start_angle, end_angle, segments):
    start_rad = math.radians(start_angle)
    end_rad = math.radians(end_angle)
    if end_rad < start_rad:
        end_rad += 2 * math.pi
    step = (end_rad - start_rad) / segments
    points = []
    for i in range(segments + 1):
        angle = start_rad + i * step
        x = center[0] + radius * math.cos(angle)
        y = center[1] + radius * math.sin(angle)
        points.append((x, y))
    return [(points[i], points[i + 1]) for i in range(len(points) - 1)]

def flatten_polyline(points, is_closed):
    segments = []
    for i in range(len(points) - 1):
        segments.append((points[i], points[i + 1]))
    if is_closed and len(points) > 2:
        segments.append((points[-1], points[0]))
    return segments

def snap_points_kdtree(points, tolerance):
    if not points:
        return {}

    points_array = np.array(list(points))
    tree = cKDTree(points_array)
    groups = tree.query_ball_tree(tree, tolerance)

    clustered = {}
    visited = set()
    for group in groups:
        cluster_indices = tuple(sorted(group))
        if not any(i in visited for i in cluster_indices):
            center = tuple(points_array[cluster_indices[0]])
            for idx in cluster_indices:
                original = tuple(points_array[idx])
                clustered[original] = center
            visited.update(cluster_indices)

    return clustered

def plot_snapped_points(original_points, snapped_points, lines):
    plt.figure(figsize=(10, 10), dpi=300)
    for start, end in lines:
        plt.plot([start[0], end[0]], [start[1], end[1]], color='lightgray', linewidth=0.3)

    for orig in original_points:
        new = snapped_points.get(orig, orig)
        if distance(orig, new) > 1e-9:
            plt.plot([orig[0], new[0]], [orig[1], new[1]], 'r-', alpha=0.6)
            plt.plot(new[0], new[1], 'go', markersize=2)
        else:
            plt.plot(orig[0], orig[1], 'bo', markersize=1)

    plt.title("Snapped Endpoints Overlaid on DXF Lines")
    plt.axis('equal')
    plt.grid(True, linestyle='--', linewidth=0.3)
    plt.savefig("snapped_points_overlay.png", bbox_inches='tight')
    print("Saved snapping visualization as: snapped_points_overlay.png")
    plt.close()

def pathwalk_reconstruct(segments, tolerance=1e-6):
    edge_map = defaultdict(list)
    for a, b in segments:
        edge_map[a].append(b)
        edge_map[b].append(a)

    used_edges = set()
    polygons = []
    open_paths = []

    def walk_path(start):
        path = [start]
        current = start

        while True:
            neighbors = edge_map[current]
            next_pt = None
            for pt in neighbors:
                edge = tuple(sorted((current, pt)))
                if edge not in used_edges:
                    used_edges.add(edge)
                    next_pt = pt
                    break
            if not next_pt:
                return path
            path.append(next_pt)
            current = next_pt
            if len(path) > 2 and distance(path[0], path[-1]) < tolerance:
                path[-1] = path[0]
                return path

    visited_pts = set()
    for pt in edge_map:
        if pt not in visited_pts:
            path = walk_path(pt)
            visited_pts.update(path)
            if len(path) > 2 and distance(path[0], path[-1]) < tolerance:
                polygons.append(path)
            else:
                open_paths.append(path)

    return polygons, open_paths

def process_dxf(input_file, output_file, unit=DEFAULT_UNIT, precision_um=DEFAULT_PRECISION_UM):
    print(f"Loading DXF file: {input_file}")
    doc = ezdxf.readfile(input_file)
    msp = doc.modelspace()

    tolerance = precision_um * UNIT_CONVERSION[unit] / 1000
    print(f"Snapping tolerance set to {tolerance} {unit} ({precision_um} µm)")

    lines = []
    all_points = set()
    arc_segments = DEFAULT_ARC_SEGMENTS

    for e in msp:
        if e.dxftype() == "LINE":
            start = (e.dxf.start.x, e.dxf.start.y)
            end = (e.dxf.end.x, e.dxf.end.y)
            lines.append((start, end))
            all_points.update([start, end])

        elif e.dxftype() == "ARC":
            center = (e.dxf.center.x, e.dxf.center.y)
            segments = flatten_arc(center, e.dxf.radius, e.dxf.start_angle, e.dxf.end_angle, arc_segments)
            lines.extend(segments)
            for seg in segments:
                all_points.update(seg)

        elif e.dxftype() == "CIRCLE":
            center = (e.dxf.center.x, e.dxf.center.y)
            segments = flatten_arc(center, e.dxf.radius, 0, 360, arc_segments)
            lines.extend(segments)
            for seg in segments:
                all_points.update(seg)

        elif e.dxftype() in ["LWPOLYLINE", "POLYLINE"]:
            if e.dxftype() == "POLYLINE":
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            else:
                pts = [tuple(p) for p in e.get_points("xy")]
            segments = flatten_polyline(pts, e.is_closed)
            lines.extend(segments)
            for seg in segments:
                all_points.update(seg)

    print(f"Total segments extracted: {len(lines)}")
    print(f"Found {len(all_points)} unique endpoints")

    snapped_map = snap_points_kdtree(all_points, tolerance)
    moved_points = {pt: snapped_map.get(pt, pt) for pt in all_points if distance(pt, snapped_map.get(pt, pt)) > 1e-9}
    print(f"{len(moved_points)} points were snapped")

    plot_snapped_points(all_points, snapped_map, lines)

    updated_lines = []
    for start, end in lines:
        new_start = snapped_map.get(start, start)
        new_end = snapped_map.get(end, end)
        updated_lines.append((new_start, new_end))

    # Deduplicate segments
    unique_segments = set(tuple(sorted([s, e])) for s, e in updated_lines)

    # Reconstruct paths
    polygons, open_paths = pathwalk_reconstruct(unique_segments)

    print(f"Closed shapes reconstructed : {len(polygons)}")
    print(f"Open paths (saved as lines) : {len(open_paths)}")

    new_doc = ezdxf.new()
    new_msp = new_doc.modelspace()
    for path in polygons:
        new_msp.add_lwpolyline(path, close=True)
    for path in open_paths:
        for i in range(len(path) - 1):
            new_msp.add_line(path[i], path[i + 1])

    new_doc.saveas(output_file)
    print(f"Saved reconstructed DXF to: {output_file}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Flatten and reconstruct DXF into clean closed shapes.")
    parser.add_argument("input", help="Input DXF file path")
    parser.add_argument("output", help="Output DXF file path")
    args = parser.parse_args()

    process_dxf(args.input, args.output)
