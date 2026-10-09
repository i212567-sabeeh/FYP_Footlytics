# ruff: noqa: E402
# Project imports follow source-path setup; this script runs without installation.
"""Held-out landmark check of a saved calibration; no database writes.

Standard pitch markings that were NOT used to fit the homography (for example the
centre spot or penalty-area corners when only the four corners were fitted) are
independent references. `crops` projects each landmark into a video frame and
saves zoomed patches with a grid so its true pixel position can be located by eye;
`score` maps the located pixels through the homography and reports the error in
metres. Visual location carries roughly +/-2 px of uncertainty; this is a sparse
spot check, not a survey. The calibration is read from a temporary database copy.
"""

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import cv2
import numpy as np

from app.cv.homography import transform_points


# FIFA standard markings (metres), X along the length and Y across the width.
def landmarks(length: float, width: float) -> dict[str, tuple[float, float]]:
    y = width / 2
    box, goal = 20.16, 9.16  # half widths of the penalty and goal areas
    points = {
        "centre_spot": (length / 2, y),
        "halfway_near_touchline": (length / 2, width),
        "halfway_far_touchline": (length / 2, 0.0),
        "centre_circle_near": (length / 2, y + 9.15),
        "centre_circle_far": (length / 2, y - 9.15),
    }
    for side, x0, sign in (("left", 0.0, 1), ("right", length, -1)):
        points |= {
            f"{side}_penalty_spot": (x0 + sign * 11, y),
            f"{side}_penalty_area_near": (x0 + sign * 16.5, y + box),
            f"{side}_penalty_area_far": (x0 + sign * 16.5, y - box),
            f"{side}_goal_area_near": (x0 + sign * 5.5, y + goal),
            f"{side}_goal_area_far": (x0 + sign * 5.5, y - goal),
        }
    return points


def calibration(database: Path, match_id: int) -> dict:
    with tempfile.TemporaryDirectory() as folder:
        copy = Path(folder) / "copy.sqlite3"
        shutil.copy2(database, copy)
        with sqlite3.connect(f"file:{copy}?mode=ro", uri=True) as connection:
            row = connection.execute(
                "SELECT id, homography_matrix, image_points, pitch_points, "
                "pitch_length_metres, pitch_width_metres, source_frame_number "
                "FROM pitch_calibrations WHERE match_id = ?",
                (match_id,),
            ).fetchone()
    keys = ("id", "matrix", "image", "pitch", "length", "width", "frame")
    data = dict(zip(keys, row, strict=True))
    for key in ("matrix", "image", "pitch"):
        data[key] = json.loads(data[key])
    return data


def crops(args) -> None:
    data = calibration(args.database, args.match_id)
    args.output.mkdir(parents=True, exist_ok=False)
    capture = cv2.VideoCapture(str(args.video))
    capture.set(cv2.CAP_PROP_POS_FRAMES, args.frame)
    ok, image = capture.read()
    capture.release()
    if not ok:
        raise SystemExit("Could not decode the requested frame")
    inverse = np.linalg.inv(np.asarray(data["matrix"], dtype=np.float64))
    fitted = [(p["x"], p["y"]) for p in data["pitch"]]
    predicted = {}
    for name, point in landmarks(data["length"], data["width"]).items():
        if any(
            abs(point[0] - x) < 1e-6 and abs(point[1] - y) < 1e-6 for x, y in fitted
        ):
            continue  # Fitted correspondences are not independent references.
        u, v = transform_points([point], inverse)[0]
        predicted[name] = (u, v)
        half, zoom = args.half, args.zoom
        x0, y0 = int(round(u)) - half, int(round(v)) - half
        patch = np.zeros((2 * half, 2 * half, 3), np.uint8)
        xs, ys = max(0, x0), max(0, y0)
        xe = min(image.shape[1], x0 + 2 * half)
        ye = min(image.shape[0], y0 + 2 * half)
        if xs < xe and ys < ye:
            patch[ys - y0 : ye - y0, xs - x0 : xe - x0] = image[ys:ye, xs:xe]
        big = cv2.resize(patch, None, fx=zoom, fy=zoom, interpolation=cv2.INTER_NEAREST)
        for step in range(0, 2 * half + 1, 10):  # grid every 10 source pixels
            colour = (90, 90, 90) if step % 50 else (160, 160, 160)
            cv2.line(big, (step * zoom, 0), (step * zoom, big.shape[0]), colour, 1)
            cv2.line(big, (0, step * zoom), (big.shape[1], step * zoom), colour, 1)
        cx, cy = int((u - x0) * zoom), int((v - y0) * zoom)
        cv2.drawMarker(big, (cx, cy), (0, 0, 255), cv2.MARKER_CROSS, 18, 1)
        cv2.putText(
            big,
            f"{name} predicted ({u:.1f}, {v:.1f}); origin ({x0}, {y0})",
            (4, 14),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (0, 255, 255),
            1,
        )
        cv2.imwrite(str(args.output / f"{name}.png"), big)
    (args.output / "predicted.json").write_text(
        json.dumps(
            {
                "calibration_id": data["id"],
                "frame": args.frame,
                "predicted_pixels": predicted,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(json.dumps(predicted, indent=1))


def score(args) -> None:
    data = calibration(args.database, args.match_id)
    located = json.loads(args.located.read_text(encoding="utf-8"))
    truth = landmarks(data["length"], data["width"])
    rows = []
    for name, pixel in located["located_pixels"].items():
        mapped = transform_points([pixel], data["matrix"])[0]
        error = float(np.hypot(mapped[0] - truth[name][0], mapped[1] - truth[name][1]))
        rows.append(
            {
                "landmark": name,
                "pixel": pixel,
                "mapped_metres": mapped,
                "true_metres": truth[name],
                "error_metres": error,
            }
        )
    errors = [row["error_metres"] for row in rows]
    result = {
        "calibration_id": data["id"],
        "landmarks": rows,
        "mean_error_metres": float(np.mean(errors)),
        "median_error_metres": float(np.median(errors)),
        "max_error_metres": float(np.max(errors)),
    }
    args.output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("crops", "score"):
        command = sub.add_parser(name)
        command.add_argument("--database", type=Path, required=True)
        command.add_argument("--match-id", type=int, required=True)
        command.add_argument("--output", type=Path, required=True)
    sub.choices["crops"].add_argument("--video", type=Path, required=True)
    sub.choices["crops"].add_argument("--frame", type=int, default=0)
    sub.choices["crops"].add_argument("--half", type=int, default=40)
    sub.choices["crops"].add_argument("--zoom", type=int, default=6)
    sub.choices["score"].add_argument("--located", type=Path, required=True)
    args = parser.parse_args()
    crops(args) if args.command == "crops" else score(args)


if __name__ == "__main__":
    main()
