import math
import argparse
import ezdxf
import matplotlib.pyplot as plt
from scipy.spatial import cKDTree
import numpy as np
from collections import defaultdict

# ===================
# CONFIGURATION BLOCK
# ===================
DEFAULT_UNIT = "mm"
DEFAULT_PRECISION_UM = 0.1
DEFAULT_ARC_SEGMENTS = 100
GAP_TOLERANCE = 1e-6
OUTPUT_SCALE = 1.0  # e.g., 0.5 for 2:1 scaling
FLIP_Y = False      # Set to True to flip vertically

UNIT_CONVERSION = {
    "mm": 1.0,
    "um": 0.001,
}

# ============
# GEOMETRY UTILS
# ============
def distance(p1, p2):
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def transform_point(pt, scale, flip_y):
    x, y = pt
    x *= scale
    y *= -scale if flip_y else scale
    return (x, y)

def flatten_arc(center, radius, start_angle, end_angle, segments):
    start_rad = math.radians(start_angle)
    end_rad = math.radians(end_angle)
    if end_rad < start_rad:
        end_rad += 2 * math.pi
    step = (end_rad - start_rad) / segments
    points = [(center[0] + radius * math.cos(start_rad + i * step),
               center[1] + radius * math.sin(start_rad + i * step))
              for i in range(segments + 1)]
    return [(points[i], points[i + 1]) for i in range(len(points) - 1)]

def flatten_polyline(points, is_closed):
    segments = [(points[i], points[i + 1]) for i in range(len(points) - 1)]
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
                clustered[tuple(points_array[idx])] = center
            visited.update(cluster_indices)
    return clustered

# ============
# VISUALIZATION
# ============
def plot_overlay(closed_paths, open_paths, snapping_events):
    plt.figure(figsize=(10, 10), dpi=300)
    for path in closed_paths:
        xs, ys = zip(*path)
        plt.plot(xs, ys, 'k-', linewidth=0.3)
    for path in open_paths:
        xs, ys = zip(*path)
        plt.plot(xs, ys, 'orange', linewidth=0.5, alpha=0.6)

    for pt in snapping_events:
        plt.plot(pt[0], pt[1], 'go', markersize=1.5, label='Snapping Point' if pt == snapping_events[0] else "")

    for path in open_paths:
        if len(path) > 1:
            plt.plot(path[0][0], path[0][1], 'ro', markersize=2, label='Open Path Start' if path == open_paths[0] else "")
            plt.plot(path[-1][0], path[-1][1], 'mo', markersize=2, label='Open Path End' if path == open_paths[0] else "")

    plt.title("Closed (black), Open (orange), Snap (green), Gaps (red/magenta)")
    handles, labels = plt.gca().get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    plt.legend(by_label.values(), by_label.keys(), fontsize='x-small')
    plt.axis('equal')
    plt.grid(True, linestyle='--', linewidth=0.3)
    plt.savefig("reconstruction_overlay.png", bbox_inches='tight')
    print("Saved path reconstruction visualization as: reconstruction_overlay.png")
    plt.close()

# ============
# PATH WALKING
# ============
def pathwalk_reconstruct(segments, tolerance=GAP_TOLERANCE):
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

# ============
# MAIN PROCESS
# ============
def process_dxf(input_file, output_file, unit=DEFAULT_UNIT, precision_um=DEFAULT_PRECISION_UM,
                scale=OUTPUT_SCALE, flip_y=FLIP_Y):
    print(f"Loading DXF file: {input_file}")
    doc = ezdxf.readfile(input_file)
    msp = doc.modelspace()

    tolerance = precision_um * UNIT_CONVERSION[unit] / 1000
    print(f"Snapping tolerance set to {tolerance} {unit} ({precision_um} µm)")
    print(f"Output scale: {scale} | Flip Y: {'Yes' if flip_y else 'No'}")

    lines, all_points = [], set()
    for e in msp:
        if e.dxftype() == "LINE":
            s, e = (e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)
            lines.append((s, e))
            all_points.update([s, e])
        elif e.dxftype() == "ARC":
            segments = flatten_arc((e.dxf.center.x, e.dxf.center.y), e.dxf.radius,
                                   e.dxf.start_angle, e.dxf.end_angle, DEFAULT_ARC_SEGMENTS)
            lines.extend(segments)
            for seg in segments: all_points.update(seg)
        elif e.dxftype() == "CIRCLE":
            segments = flatten_arc((e.dxf.center.x, e.dxf.center.y), e.dxf.radius, 0, 360, DEFAULT_ARC_SEGMENTS)
            lines.extend(segments)
            for seg in segments: all_points.update(seg)
        elif e.dxftype() in ["POLYLINE", "LWPOLYLINE"]:
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices] if e.dxftype() == "POLYLINE" else [tuple(p) for p in e.get_points("xy")]
            segments = flatten_polyline(pts, e.is_closed)
            lines.extend(segments)
            for seg in segments: all_points.update(seg)

    snapped_map = snap_points_kdtree(all_points, tolerance)
    snapping_events = [pt for pt in all_points if distance(pt, snapped_map.get(pt, pt)) > 1e-9]
    print(f"Snapping events: {len(snapping_events)}")

    updated_lines = [(snapped_map.get(s, s), snapped_map.get(e, e)) for s, e in lines]
    unique_segments = set(tuple(sorted([s, e])) for s, e in updated_lines)

    closed_shapes, open_paths = pathwalk_reconstruct(unique_segments)
    print(f"Closed shapes reconstructed: {len(closed_shapes)}")
    print(f"Open paths (not closed):      {len(open_paths)}")

    # Transform and write output DXF
    new_doc = ezdxf.new()
    new_msp = new_doc.modelspace()
    for path in closed_shapes:
        new_msp.add_lwpolyline([transform_point(p, scale, flip_y) for p in path], close=True)
    for path in open_paths:
        for i in range(len(path) - 1):
            new_msp.add_line(transform_point(path[i], scale, flip_y), transform_point(path[i + 1], scale, flip_y))
    new_doc.saveas(output_file)
    print(f"Saved cleaned DXF to: {output_file}")

    # Visualization
    plot_overlay(closed_shapes, open_paths, snapping_events)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DXF reconstruction with scaling and flipping options.")
    parser.add_argument("input", help="Input DXF file path")
    parser.add_argument("output", help="Output DXF file path")
    args = parser.parse_args()
    process_dxf(args.input, args.output)
