# Nanorod Detection Parameter Guide

This guide details the key parameters used in the detection algorithm and their recommended values for different scenarios.

## Current Settings (AutoDetect-mNP)

We are using the **AutoDetect-mNP** algorithm (Wang et al.):
1.  **K-means Segmentation**: Robustly separates foreground/background using clustering.
2.  **rUECS (Recursive Erosion)**: Intelligently splits clumps by eroding them until they break into convex parts, then growing them back.

| Parameter | Status | Description |
| :--- | :--- | :--- |
| **Segmentation** | `K-means + rUECS` | Clustering + Recursive Erosion for clumps. |
| **Aspect Ratio** | `Disabled` | Fitting all detected objects. |
| **Solidity** | `Disabled` | Fitting all detected objects. |
| **Containment** | `Disabled` | Fitting all detected objects. |

**Note**: Manual parameters like `Separation`, `Closing`, and `Threshold` are no longer used.

## Parameter Effects

### 1. Aspect Ratio (`aspect_ratio_px`)
- **What it does**: Filters out objects that are too round (spheres).
- **Increase (e.g., 2.0)**: Only detects very long, thin rods.
- **Decrease (e.g., 1.1)**: Detects almost everything, including spheres and impurities.

### 2. Solidity (`solidity`)
- **What it does**: Checks how "solid" the object is compared to a perfect ellipse.
- **Increase (e.g., 0.9)**: Only detects perfect, smooth ellipses.
- **Decrease (e.g., 0.5)**: Accepts very jagged or distorted shapes.

### 3. Separation Distance (`target_dist_nm`)
- **What it does**: Controls how far apart two rod centers must be to be counted as separate objects.
- **Increase (e.g., 20nm)**: Prevents splitting a single rod into two, but might merge touching rods.
- **Decrease (e.g., 5nm)**: Separates touching rods well, but might split a single rod into multiple pieces.

### 4. Morphological Closing (`closing_radius_nm`)
- **What it does**: Connects fragmented parts of a rod.
- **Current**: `1.0 nm` (Conservative).
- **Note**: Increasing this too much (>3nm) can cause rods to merge together.

## How to Adjust
To adjust these parameters, modify the variables at the top of the `process_image` function in `backend/processing.py`.
