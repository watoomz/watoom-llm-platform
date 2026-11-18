#!/usr/bin/env python3
"""Find where terrain buries a creek's water ("the creek ends and starts again").

Two steps, no Unreal code in this file:
  unreal_creek_check.py trace  --spline river_calls.txt --out trace.json     writes a level.bulk_line_trace request (straight down over every spline point)
  unreal_creek_check.py report --spline river_calls.txt --trace trace_out.txt [--tol 30]   reads the trace answer and lists the buried stretches

The spline file is the text of the `level.set_component_property ... SplineCurves` call (or any file containing
`InVal=N,OutVal=(X=..,Y=..,Z=..)` position entries). Points whose water Z is more than --tol cm below the ground hit by
the trace are buried; a first hit on a lake or other actor is reported as such and not counted. Exit code 1 when buried
stretches exist, so it can gate a rebuild.
"""
import argparse
import json
import re
import sys

POINT = re.compile(r"InVal=([\d.]+),OutVal=\(X=([-\d.]+),Y=([-\d.]+),Z=([-\d.]+)\)")


def spline_points(text):
    """Position points only: the Position curve comes first; Rotation/Scale entries repeat the InVal list after it."""
    pts, last = [], -1.0
    for inval, x, y, z in POINT.findall(text):
        if float(inval) <= last:
            break
        last = float(inval)
        pts.append((float(x), float(y), float(z)))
    return pts


def trace_request(pts, top=20000.0):
    return {"traces": [{"start": {"x": x, "y": y, "z": top}, "end": {"x": x, "y": y, "z": 0}} for x, y, _ in pts]}


def analyse(pts, results, tol=30.0, landscape="Landscape"):
    """Rows of (index, water_z, ground_z or None, gap, state) and the buried runs as (first, last) index pairs."""
    rows = []
    for i, ((_, _, wz), r) in enumerate(zip(pts, results)):
        if not r.get("hit"):
            rows.append((i, wz, None, None, "nohit"))
            continue
        label = str(r.get("actorLabel", ""))
        gz = (r.get("location") or r.get("impactPoint") or {}).get("z")
        if landscape.lower() not in label.lower():
            rows.append((i, wz, gz, None, "other:" + label))
            continue
        gap = gz - wz
        rows.append((i, wz, gz, gap, "buried" if gap > tol else "ok"))
    runs, start = [], None
    for i, _, _, _, st in rows + [(len(rows), 0, 0, 0, "end")]:
        if st == "buried" and start is None:
            start = i
        elif st != "buried" and start is not None:
            runs.append((start, i - 1))
            start = None
    return rows, runs


def load_trace_output(text):
    return json.loads(text[text.index("{"):])["results"]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("trace")
    t.add_argument("--spline", required=True)
    t.add_argument("--out", required=True)
    r = sub.add_parser("report")
    r.add_argument("--spline", required=True)
    r.add_argument("--trace", required=True)
    r.add_argument("--tol", type=float, default=30.0)
    a = ap.parse_args(argv)
    pts = spline_points(open(a.spline).read())
    if a.cmd == "trace":
        json.dump(trace_request(pts), open(a.out, "w"))
        print("wrote %s: %d points" % (a.out, len(pts)))
        return 0
    rows, runs = analyse(pts, load_trace_output(open(a.trace).read()), a.tol)
    for i, wz, gz, gap, st in rows:
        print("%3d water %7.0f ground %s gap %s %s" % (i, wz, "%7.0f" % gz if gz is not None else "   none", "%+5.0f" % gap if gap is not None else "  n/a", st))
    print("buried stretches (point index ranges): %s" % (runs or "none"))
    return 1 if runs else 0


if __name__ == "__main__":
    sys.exit(main())
