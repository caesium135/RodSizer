# RodSizer Parameter Guide

This guide explains the main processing parameters that are currently active in RodSizer.

## Current Detection Flow

The current backend uses an AutoDetect-mNP-style workflow in `backend/processing.py`:

1. `K-means segmentation` separates foreground particles from background.
2. `Scale bar masking` removes the scale bar area so it is not detected as a particle.
3. `Solidity-based split logic` decides whether an object is treated as a single particle or sent to `rUECS` for clump splitting.
4. `Measurement` uses `minAreaRect` to estimate rod length and width.
5. `Post-analysis clustering` uses aspect ratio, solidity, and circularity for class-colored overlay grouping.

## Parameters Currently In Use

| Parameter | Current Value / Behavior | What it does |
| :--- | :--- | :--- |
| `requested_bar_length_nm` | `200.0` nm default | Draws a synthetic blue scale bar if a real calibration is available and no override is given. |
| `manual_pixel_size` | Optional user override | Replaces metadata-based calibration when supplied. |
| `min_area_nm2` | `30` nm^2 | Rejects very small objects as noise before and after segmentation. |
| `region.solidity > 0.9` | Active | Treats highly convex objects as simple particles; lower-solidity objects are treated as clumps and split with `rUECS`. |
| Overlap threshold | `0.15` | Used during non-maximum suppression to skip heavily overlapping duplicate detections. |
| K-means classes | Up to `4` groups | Groups detected particles for the colored overlay using aspect ratio, solidity, and circularity. |

## Measurement and Descriptor Outputs

These values are computed for each accepted particle:

- `length_nm`
- `width_nm`
- `aspect_ratio`
- `volume_nm3`
- `orientation_deg`
- `area_px`
- `solidity`
- `convexity`
- `circularity`
- `eccentricity`

Important: in the current code, `aspect_ratio`, `solidity`, and `circularity` are mainly measurement/classification descriptors. They are not user-facing manual filter knobs in the current workflow.

## Parameters No Longer Used As Manual Controls

The following items described in older documentation are not active as manual tuning parameters in the current `process_image` workflow:

- `target_dist_nm`
- `closing_radius_nm`
- manual threshold controls such as `Threshold`
- older separation/closing sliders or variables
- `aspect_ratio_px` as a direct hard filter
- `containment` as a direct hard filter

## Practical Effect of the Active Parameters

### 1. Minimum Area (`min_area_nm2`)
- Removes tiny specks, dirt, and segmentation noise.
- Increasing it makes detection more conservative.
- Decreasing it allows smaller objects through, but may increase false positives.

### 2. Solidity Split Threshold (`region.solidity > 0.9`)
- High-solidity objects are treated as single particles.
- Lower-solidity objects are assumed to be clumps or irregular shapes and are sent to `rUECS`.
- Increasing this threshold makes the app split more borderline shapes as clumps.
- Decreasing this threshold makes the app keep more irregular shapes as single objects.

### 3. Manual Pixel Size (`manual_pixel_size`)
- Overrides image metadata calibration.
- Useful when metadata is missing or incorrect.
- A wrong value will directly affect all reported dimensions in nanometers.

### 4. Requested Scale Bar Length (`requested_bar_length_nm`)
- Controls the displayed synthetic scale bar length.
- Default is `200 nm`.
- This affects the visualization scale bar, not particle detection itself.

## Where To Adjust These Parameters

If you want to change the current defaults, look in:

- [backend/processing.py](/Users/shichen/Documents/GitHub/RodSizer/backend/processing.py)

The main place to inspect is the `process_image(...)` function.
