from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_JSON = PROJECT_ROOT / "models" / "reliefcheck-kiosk-v1.json"
OUTPUT_STL = PROJECT_ROOT / "models" / "reliefcheck-kiosk-v1.stl"

Point = tuple[float, float, float]
Triangle = tuple[Point, Point, Point]


def main() -> None:
    model = json.loads(MODEL_JSON.read_text(encoding="utf-8"))
    triangles: list[Triangle] = []
    for component in model["components"]:
        kind = component["type"]
        if kind == "box":
            triangles.extend(box_triangles(component["position"], component["size"]))
        elif kind == "rotated_box":
            triangles.extend(
                box_triangles(
                    component["position"],
                    component["size"],
                    rotation_x_deg=float(component.get("rotation_x_deg", 0)),
                )
            )
        elif kind == "cylinder":
            triangles.extend(
                cylinder_triangles(
                    component["position"],
                    radius=float(component["radius"]),
                    height=float(component["height"]),
                    segments=32,
                )
            )
        else:
            raise ValueError(f"unsupported component type: {kind}")

    write_ascii_stl(OUTPUT_STL, "reliefcheck_kiosk_v1", triangles)
    print(f"wrote {OUTPUT_STL}")


def box_triangles(
    center: Iterable[float],
    size: Iterable[float],
    rotation_x_deg: float = 0,
) -> list[Triangle]:
    cx, cy, cz = map(float, center)
    sx, sy, sz = (value / 2 for value in map(float, size))
    corners = [
        (-sx, -sy, -sz),
        (sx, -sy, -sz),
        (sx, sy, -sz),
        (-sx, sy, -sz),
        (-sx, -sy, sz),
        (sx, -sy, sz),
        (sx, sy, sz),
        (-sx, sy, sz),
    ]
    transformed = [translate(rotate_x(point, rotation_x_deg), (cx, cy, cz)) for point in corners]
    faces = [
        (0, 3, 2, 1),
        (4, 5, 6, 7),
        (0, 1, 5, 4),
        (1, 2, 6, 5),
        (2, 3, 7, 6),
        (3, 0, 4, 7),
    ]
    triangles: list[Triangle] = []
    for a, b, c, d in faces:
        triangles.append((transformed[a], transformed[b], transformed[c]))
        triangles.append((transformed[a], transformed[c], transformed[d]))
    return triangles


def cylinder_triangles(
    center: Iterable[float],
    radius: float,
    height: float,
    segments: int,
) -> list[Triangle]:
    cx, cy, cz = map(float, center)
    bottom_z = cz - height / 2
    top_z = cz + height / 2
    top_center = (cx, cy, top_z)
    bottom_center = (cx, cy, bottom_z)
    triangles: list[Triangle] = []
    for index in range(segments):
        a0 = 2 * math.pi * index / segments
        a1 = 2 * math.pi * (index + 1) / segments
        bottom0 = (cx + radius * math.cos(a0), cy + radius * math.sin(a0), bottom_z)
        bottom1 = (cx + radius * math.cos(a1), cy + radius * math.sin(a1), bottom_z)
        top0 = (bottom0[0], bottom0[1], top_z)
        top1 = (bottom1[0], bottom1[1], top_z)
        triangles.append((bottom0, bottom1, top1))
        triangles.append((bottom0, top1, top0))
        triangles.append((top_center, top0, top1))
        triangles.append((bottom_center, bottom1, bottom0))
    return triangles


def rotate_x(point: Point, degrees: float) -> Point:
    if degrees == 0:
        return point
    x, y, z = point
    radians = math.radians(degrees)
    cos_v = math.cos(radians)
    sin_v = math.sin(radians)
    return (x, y * cos_v - z * sin_v, y * sin_v + z * cos_v)


def translate(point: Point, offset: Point) -> Point:
    return (point[0] + offset[0], point[1] + offset[1], point[2] + offset[2])


def normal(triangle: Triangle) -> Point:
    a, b, c = triangle
    ux, uy, uz = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    vx, vy, vz = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def write_ascii_stl(path: Path, name: str, triangles: list[Triangle]) -> None:
    lines = [f"solid {name}"]
    for triangle in triangles:
        nx, ny, nz = normal(triangle)
        lines.append(f"  facet normal {nx:.6f} {ny:.6f} {nz:.6f}")
        lines.append("    outer loop")
        for vertex in triangle:
            lines.append(f"      vertex {vertex[0]:.3f} {vertex[1]:.3f} {vertex[2]:.3f}")
        lines.append("    endloop")
        lines.append("  endfacet")
    lines.append(f"endsolid {name}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
