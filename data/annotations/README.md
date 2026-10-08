# FOOTLYTICS validation annotations

Annotations are human-checked answers used to measure model errors. A person draws
player boxes, follows player identities through frames, and records their teams.
FOOTLYTICS predictions are then compared with those answers. Predictions alone,
manual team overrides in the application, and unit-test fixtures are not ground truth.

## Current inventory and annotation work

The manual-footage folders `data/validation_clips/`, `data/sample/` and the
header-only templates here were empty when the evaluator was first implemented.
Phase 15 now includes real SoccerNet-GSR evidence under
`data/external/soccernet_gsr/`: **3 clips from 3 source games, 450 reviewed frames,
6,603 scored player/GK boxes, 49 GT tracks and 49 team-labelled tracks**. Real
accuracy and CPU throughput are reported in the SoccerNet section below and the
project README. Verified independent calibration landmarks remain **0**, so
calibration/player-coordinate accuracy remains unavailable. Templates themselves
are still placeholders, not real annotations.

A practical starting plan is below. These are **proposed filenames and frames**;
the footage does not currently exist here. Choose three short clips with at least
100 frames each, ideally 10–20 seconds, independently of pipeline development.

| Proposed footage under `data/validation_clips/` | Initial reviewed frames | Variation |
| --- | --- | --- |
| `val_5v5_daylight.mp4` | Every frame 0–99 | Nearby camera, visible jerseys |
| `val_11v11_wide.mp4` | Every frame 0–99 | Distant players, greater density |
| `val_occlusion.mp4` | Every frame 0–99 | Partial occlusions, different lighting/colors |

For each clip create `<clip_id>.frames.csv` and `<clip_id>.boxes.csv` using the
header-only templates. Mark **all** visible players in each reviewed frame, with
consistent identities and team labels where known. Keep identity review continuous
within each segment; additional sparse frames can supplement detection evaluation.
Record actual format, source, duration, dimensions, FPS, conditions and reviewer in
`dataset.json`. Unreviewed frames must never be interpreted as empty ground truth.

If possible, also create `<clip_id>.landmarks.csv`: at least four well-spread fit
points plus separately selected validation landmarks visible in one camera pose.
Record the actual Match pitch length/width. Player pitch coordinates are optional
and require independent measurements. Do not fill them from FOOTLYTICS homography.

## Canonical CSV conventions

Use UTF-8 and ordinary CSV quoting. Frame numbers are **zero-based decoded video
indices**, starting at 0. Timestamps are seconds from the start of this exact clip,
using decoded presentation time; for constant-FPS footage, `frame_number / fps`
is suitable. Do not use rounded display time if it differs by more than 1 ms.

`frames.csv` declares every reviewed frame, including frames with **zero players**:

| Column | Meaning |
| --- | --- |
| `clip_id` | Manifest clip ID, unique across this dataset |
| `frame_number` | Non-negative frame index within this clip |
| `timestamp_seconds` | Finite, non-negative timestamp |
| `tracking_evaluable` | `true` when every scored player has a reliable GT identity; otherwise `false` |

`boxes.csv` uses the columns in `boxes.template.csv`:

| Columns | Convention |
| --- | --- |
| `clip_id, frame_number, timestamp_seconds` | Must match a reviewed frame |
| `ground_truth_track_id` | Human-assigned identity, stable within this clip; blank permitted on detection-only frames |
| `x1,y1,x2,y2` | Original-image pixels: left/top/right/bottom; continuous edges, area `(x2-x1)*(y2-y1)`, no `+1` |
| `team_label` | `team_a`, `team_b`, genuinely uncertain `unknown`, `official`, or blank if not annotated |
| `ignored` | `true` for an explicitly excluded/ambiguous box, otherwise `false` |
| `pitch_x,pitch_y` | Both blank unless independently measured; metres, X=length and Y=width |

Boxes must satisfy `0 <= x1 < x2 <= image_width` and the analogous Y bounds. Use
the visible person extent, including the visible lower body. Clip at image edges.
Partially visible players remain included when a reliable box can be drawn.
Document this visible-box convention when comparing with datasets using amodal boxes.

For fully hidden players, emit no box during invisibility. Retain their identity
on reappearance only when a human can establish it reliably. Never reuse a GT ID
for a different player, and never compare IDs across clips. If identity is ambiguous,
mark the frame detection-only or split the validation segment and document it;
do not invent identity continuity. Track IDs identify observations, not roster names.

Annotate officials as `official`; they are ignored for this player-only protocol.
Do not count them as Team A/B players. Unknown-team players still count for
detection/tracking. GT `unknown`/official tracks are excluded from team-accuracy
denominators. Blank means not annotated, rather than a confirmed Unknown label.

Ignore policy: first match scored players one-to-one, then suppress unmatched
predictions with IoU above threshold against explicitly ignored/official boxes.
Report the ignored count. Do not create broad ignore boxes to conceal errors.
This local policy is documented and is not an official MOTChallenge submission.

## Team-color mapping

The Phase 8 automatic classifier assigns deterministic cluster names; these are not
semantic home/away labels. Decide and document each clip's jersey correspondence
before examining accuracy scores. Supply `team_mapping` mapping **automatic labels
to GT labels**, e.g. `{"team_a":"team_b","team_b":"team_a"}`, and explain the
jersey evidence in `team_mapping_basis`. Do not choose a swap by maximizing test
accuracy. Unknown stays Unknown. If the correspondence cannot be established,
leave mapping null and report team evaluation unavailable.

The scorer links GT identities to predicted track IDs using per-frame IoU matches
and a maximum total matched-frame assignment, without looking at team labels.
Each eligible GT Team A/B identity is counted once. Unassociated identities and
missing/Unknown automatic predictions count as Unknown, lowering coverage and
overall accuracy. It also reports accuracy among classified tracks and association
coverage, so tracking failures are visible. This is a track-aligned pipeline score,
not a classifier score measured with perfect ground-truth tracks.

## Calibration and independent positions

`landmarks.csv` has the columns in `landmarks.template.csv`. Use a unique
`landmark_id`, one declared `frame_number`, original `image_x,image_y`, independent
`pitch_x,pitch_y`, and `role=fit` or `role=validation`. Pitch coordinates must come
from known/measured pitch markings and actual Match dimensions. IDs, image points
and pitch points cannot be reused between fitting and validation sets.

The existing homography implementation fits only `fit` rows. Error is calculated
only on `validation` rows. Four fitting points alone establish no generalization
accuracy. Record camera pose; a fixed-frame result does not validate a moving camera.
P95 remains unavailable until there are at least 20 independent observations in
the reported group. Correlated measurements and small samples limit interpretation.

For player-position evaluation, describe the independent measurement source in
`pitch_ground_truth_method` and set `independent_pitch_ground_truth=true`. A second
copy of the same estimated homography is not independent evidence. The evaluator
matches Phase 9 boxes to GT boxes, compares matched coordinates in metres, and
reports unmatched GT positions alongside error. Without this evidence, leave both
coordinate cells blank. No real trajectory-cleaning accuracy is then claimed.

## Optional CVAT workflow

[CVAT's XML video format](https://docs.cvat.ai/docs/dataset_management/formats/format-cvat/)
exports tracks and per-frame boxes. Create a video task for the exact clip, use
player/official labels and a team attribute, and review every selected frame.
Review interpolation and any assisted annotations manually before export.

Export CVAT XML and convert selected reviewed entries to these canonical CSVs:

| CVAT field | Canonical field |
| --- | --- |
| task's declared clip identifier | `clip_id` |
| box `frame` | `frame_number` (preserve zero-based indexing) |
| track `id` | `ground_truth_track_id` |
| `xtl,ytl,xbr,ybr` | `x1,y1,x2,y2` |
| team attribute / official label | `team_label` |
| `outside=1` | Omit box for that frame |

`occluded=1` alone does not mean ignore: apply the visible-box policy above. Derive
timestamps from the original clip and separately list all reviewed frames, even
empty ones. The evaluator consumes the canonical CSVs, not CVAT XML; this field
mapping documents conversion, and no external annotation tool is an app dependency.

## Dataset manifest

Copy `dataset.template.json` to ignored `dataset.json`. Add actual clips using
this structure (replace every placeholder; this example contains no observations):

```json
{
  "clip_id": "val_5v5_daylight",
  "video": {"path": "../validation_clips/val_5v5_daylight.mp4", "sha256": "REPLACE_WITH_SHA256"},
  "frames": {"path": "val_5v5_daylight.frames.csv", "sha256": "REPLACE_WITH_SHA256"},
  "annotations": {"path": "val_5v5_daylight.boxes.csv", "sha256": "REPLACE_WITH_SHA256"},
  "fps": 25,
  "frame_count": 250,
  "width": 1920,
  "height": 1080,
  "duration_seconds": 10,
  "football_format": "5v5",
  "conditions": "Replace with actual lighting, camera, density and occlusion",
  "team_mapping": {"team_a": "team_a", "team_b": "team_b"},
  "team_mapping_basis": "Replace with independently recorded jersey-color correspondence"
}
```

The numerical metadata above is illustrative, not an available dataset. Replace
it with the clip's metadata. Optional fields are `landmarks` (a file/hash reference),
`calibration_frame_number`, both pitch dimensions, and independent player-position
provenance. Record annotation author/review notes and attest independent human GT
only after it exists. Paths are relative to the containing manifest. Obtain file
hashes with `sha256sum filename` in WSL. Hash the completed dataset manifest last.

## Reusing FOOTLYTICS predictions

Use artifacts generated from the **exact validation clip bytes**, at the recorded
configuration. A trimmed/re-encoded version or a full Match with different frame
offsets is not interchangeable. Use successful, current pipeline jobs; check their
source video/calibration/result versions before assembling the offline manifest.
The offline evaluator verifies bytes/configuration but cannot certify an operator's
false provenance claim or independently prove that a label was drawn by a human.

Copy `predictions.template.json` outside the annotation directory, for example
`storage/evaluation_inputs/predictions.json`. Fill in the generation time (UTC),
dataset SHA-256, software versions, source revision/checksum and exact model weights
file/hash. Populate `pipeline_config` with the CV-only snapshot captured **when the
predictions were generated**:

```bash
cd '/mnt/d/VS Projects/FYP_Footlytics/backend'
source /home/sabeeh/.venvs/footlytics-yolo/bin/activate
python -m app.evaluation.run --write-config ../storage/evaluation_inputs/pipeline_config.json
```

Create the destination folder first. The snapshot command refuses to overwrite an
existing file. It records YOLO/confidence/image size/person filter/device/stride/ROI,
ByteTrack, team thresholds and trajectory settings, without credentials. Do not
substitute today's settings for unknown settings of an earlier job. Do not tune
thresholds repeatedly on the validation set. Record any justified defect fix.

Each prediction clip entry declares `clip_id`, `video_sha256`,
`pipeline_config_sha256`, the complete sorted `processed_frames` list (including
frames with zero detections), and optional file/hash references named `detections`,
`tracks`, `automatic_teams`, `coordinates`, `cleaned`, `calibration`.
`pipeline_config_sha256` is SHA-256 of the parsed config encoded with
`json.dumps(config, sort_keys=True, separators=(",", ":"), allow_nan=False)`.
Use `app.evaluation.configuration.digest_json` to obtain it.

Detection/tracking/coordinate/cleaned CSVs retain their existing FOOTLYTICS columns.
Export team rows from the same tracking version with
`track_id,automatic_team,automatic_confidence`. The evaluator ignores
`manual_team`/`effective_team`; an effective-only export is rejected. Missing
automatic rows count as Unknown. Save the original automatic values before any
manual corrections and retain the job/version evidence.

Coordinates require a calibration JSON reference containing `video_sha256`,
`frame_number`, `pitch_length_metres`, `pitch_width_metres`, and the saved 3×3
`matrix`. Every reviewed frame must appear in prediction coverage. Missing files,
changed hashes, malformed rows or wrong dimensions/frame IDs abort scoring and
produce diagnostics. All input hashes are checked again before output publication.

## Running and interpreting evaluation

Install only the separate evaluation dependencies in the existing WSL environment:

```bash
python -m pip install -r requirements-evaluation.lock
python -m app.evaluation.run --inventory --probe-torch
python -m app.evaluation.run \
  --dataset ../data/annotations/dataset.json \
  --predictions ../storage/evaluation_inputs/predictions.json \
  --output ../storage/evaluation --probe-torch
```

The CLI reuses declared artifacts; it does not rerun YOLO or scan production Match
storage. Limits are 20 clips, 10,000 reviewed/processed frames per clip, and 200,000
rows per CSV. This is for short validation clips; it is not a full-season benchmark.

Detection reports TP/FP/FN, precision, recall, F1 and mean matched IoU at IoU ≥ 0.50.
Assignment maximizes above-threshold match count, then total IoU, so a strong match
cannot displace two valid matches. AP50 uses confidence ordering and the all-points
interpolated precision envelope at IoU 0.50, with confidence-ordered matching
before ignored-region suppression; duplicate player hits remain false positives.
It includes the saved score floor and
missing recall; it is not COCO mAP or mAP50:95. Undefined ratios are null.

[motmetrics](https://github.com/cheind/py-motmetrics) supplies IDF1, MOTA, MOTP,
switches, false positives, misses, fragmentations and mostly tracked/lost counts.
MOTP is the library's mean distance **1 − IoU**, so smaller is better; it is not an
IoU percentage. Each clip has its own accumulator; overall metrics use library
aggregation rather than averaging clip percentages. Sparse annotation is evaluated
only on reviewed frames and cannot reveal intervening switches.

Team output includes a confusion matrix, class precision/recall/F1, overall and
classified-only accuracy, Unknown rate and coverage. Coverage is Team A/B
predictions divided by eligible GT Team A/B identities. Calibration/player-coordinate
output uses mean/median/RMSE/max and P95 where supported, all in metres.

Each unique output directory contains JSON summary/configuration, a Markdown
evaluation report, detection/tracking/team/coordinate/runtime CSVs, confusion
matrix and invalid-row diagnostics. Per-clip results stay visible beside aggregate
results. Missing metrics have an explicit reason; processing counts are diagnostics.

## Runtime measurement

`--probe-torch` records actual machine/Python/library versions and CUDA availability.
The scorer's elapsed time is **not** YOLO throughput. To report stage runtime, time
an explicit short validation-clip run of the existing pipeline with
`time.perf_counter()`. Measure loading/download/warm-up separately. For each stage,
record elapsed seconds, processed frame count, device, hardware, whether setup is
included and exactly what operations were inside the timer. Include frame decoding
and I/O in the method description when included; do not use queue waiting time.

Optional per-clip `runtime` entries use `stage` (`detection`, `tracking`,
`team_classification`, `coordinate_mapping`), `seconds`, `frames`, `device`,
`setup_included`, `hardware`, and `measurement_method`. These must be actual
measurements from the artifact-producing run. FPS is frames/seconds. Without
measurements, runtime stays unavailable. CPU is sufficient; do not imply GPU speed.

## Synthetic checks and completion

```bash
python -m pytest tests/test_evaluation_metrics.py tests/test_evaluation_inputs.py tests/test_evaluation_validation.py -q
```

Synthetic manifests require `provenance=synthetic`, synthetic prediction provenance
and `--allow-synthetic`. Outputs carry **SYNTHETIC TEST — NOT REAL MODEL ACCURACY**
and a `synthetic-` directory prefix. They test evaluator mathematics and file handling
only. Keep them out of empirical headline metrics. The real SoccerNet evaluation
below is separate; manual user-footage validation can use the preserved guide above.


## SoccerNet-GSR external validation (Phase 15 complete)

The manual/CVAT workflow above remains available. The additional adapter
`app.evaluation.adapters.soccernet_gsr` supports the inspected **1.3** schema in
[SN-GSR-2025](https://huggingface.co/datasets/SoccerNet/SN-GSR-2025), `valid.zip`,
revision `ce84ee7d9acb2f9fe999ceed2b38e303ffa5efb9`. Original annotations/JPEGs are
independent of FOOTLYTICS. Human keyframe labels include dataset interpolation;
external calibrated pitch estimates are not surveyed athlete positions.

Frozen metadata-only selection: SNGS-021/game 2, SNGS-039/game 3, SNGS-078/game 5,
first suitable clip per new source game in sorted validation order. All 37 skipped
clips and reasons are retained. Never reselect using accuracy. Source images
000001..000150 become consecutive frames 0..149, 25 FPS, 1920 x 1080. Totals:
450 frames, 18 seconds, 6,603 scored player/GK boxes and 49 team-labelled identities;
642 referee boxes are ignored. Ball/pitch/camera records do not become players.
Opaque image IDs join filenames; pixel xywh boxes become xyxy without resizing.
Invalid/inconsistent GT is rejected without invented labels, clipping or repairs.

Mapping uses **jersey-color references extracted from human-labelled SoccerNet team
annotations**, not assistant judgments described as human labels. Fixed GT outfield
crops on frames 0,15,30 give median Lab references ordered by (L,a,b). 021/039:
left -> A, right -> B; 078: right -> A, left -> B. Save references/mappings before
inference. Do not use manual overrides or an accuracy-maximizing permutation.

Original member checks/hashes and the selection audit live under
`data/external/soccernet_gsr/`. Its `converted/distinct-games-v1/dataset.json` and
`provenance.json` freeze canonical CSVs, source hashes, roles, references and
configuration. Lossless PNG-in-MOV preparation compares every production-decoded
frame with its decoded source JPEG: 450 checked, zero mismatches. Visual alignment
checks cover source 000001/000076/000150 -> production/evaluator 0/75/149.

Use the existing WSL Python environment from `backend/`:

```bash
# Already prepared: reuse the frozen manifest. For an unprepared copy only:
# python -m app.evaluation.soccernet --root ../data/external/soccernet_gsr

# First-clip smoke. Matching cached predictions are reused without YOLO.
python -m app.evaluation.predict \
  --dataset ../data/external/soccernet_gsr/converted/distinct-games-v1/dataset.json \
  --output ../storage/evaluation_inputs/soccernet-gsr-distinct-games-v1 --clip SNGS-021
python -m app.evaluation.soccernet_report \
  --dataset ../data/external/soccernet_gsr/converted/distinct-games-v1/dataset.json \
  --predictions ../storage/evaluation_inputs/soccernet-gsr-distinct-games-v1/predictions.json \
  --output ../storage/evaluation/soccernet-gsr-smoke --smoke

# After first-clip validation, run/reuse the remaining frozen clips.
python -m app.evaluation.predict \
  --dataset ../data/external/soccernet_gsr/converted/distinct-games-v1/dataset.json \
  --output ../storage/evaluation_inputs/soccernet-gsr-distinct-games-v1
python -m app.evaluation.soccernet_report \
  --dataset ../data/external/soccernet_gsr/converted/distinct-games-v1/dataset.json \
  --predictions ../storage/evaluation_inputs/soccernet-gsr-distinct-games-v1/predictions.json \
  --output ../storage/evaluation/soccernet-gsr
```

The runner refuses changed settings/source/weights/dataset fingerprints and never
combines stale predictions or overwrites completed artifacts. It uses existing YoloPlayerDetector,
ByteTrackTracker and automatic classification; pitch ROI is unavailable without
verified corners. Calibration/job sentinel fields are offline metadata only; no
application Match records are created. Tests use tiny synthetic fixtures without
model downloads. Frozen source manifests/media must accompany reproduction;
they are intentionally ignored by Git.

The real report is under
`storage/evaluation/soccernet-gsr/20261005T190256Z-b2071b05c157/`, with per-clip/
aggregate results, runtime and configuration/hashes. Overall detection F1/AP50:
87.01%/81.40%; tracking IDF1/MOTA: 76.44%/73.09%. Team accuracy/coverage: 6.12%;
46/49 eligible identities are Unknown. Classified-only 100% covers only three.
Calibration/pitch-coordinate accuracy lacks verified fit and separate held-out
landmarks; `coordinate_metrics.csv` is omitted. Never invent correspondences from
line samples/player GT or assume static calibration across a moving camera.

Only 18 seconds from three broadcast 11v11 games were evaluated. Camera motion,
zoom, lighting, player scale and compression limit transfer to user recordings
and 5v5. No broad football/full-match trajectory or reliable team-identification
accuracy is claimed. Phase 16 remains pending.
