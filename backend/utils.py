from pathlib import Path
import json
import ncempy.io as nio
import tifffile
import cv2
import numpy as np
import pytesseract
import re
from PIL import Image
import h5py
import xml.etree.ElementTree as ET

def _convert_to_nm(value, unit):
    """Convert a pixel size value from given unit to nanometers."""
    unit = unit.lower().strip()
    conversions = {
        'nm': 1, 'nanometer': 1, 'nanometers': 1,
        'um': 1e3, 'µm': 1e3, 'micrometer': 1e3, 'micrometers': 1e3, 'micron': 1e3, 'microns': 1e3,
        'mm': 1e6, 'millimeter': 1e6, 'millimeters': 1e6,
        'cm': 1e7, 'centimeter': 1e7, 'centimeters': 1e7,
        'm': 1e9, 'meter': 1e9, 'meters': 1e9,
        'inch': 2.54e7, 'inches': 2.54e7,
    }
    factor = conversions.get(unit)
    if factor is not None:
        return value * factor
    return None


def _decode_tiff_tag_texts(value):
    """Yield searchable text variants from TIFF tag values, including raw bytes."""
    if value is None:
        return []

    texts = []
    if isinstance(value, bytes):
        for encoding in ("latin1", "utf-8", "utf-16le"):
            try:
                decoded = value.decode(encoding, errors="ignore")
            except Exception:
                continue
            if decoded:
                texts.append(decoded)
    else:
        try:
            text = str(value)
        except Exception:
            text = ""
        if text:
            texts.append(text)

    variants = []
    seen = set()
    for text in texts:
        for candidate in (text, text.replace("\x00", "")):
            if candidate and candidate not in seen:
                seen.add(candidate)
                variants.append(candidate)
    return variants


def _normalize_h5_attr(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="ignore")
    return value


def _coerce_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _emd_dataset_to_2d(raw):
    """Reduce common EMD dataset layouts to a 2D image plane."""
    arr = np.asarray(raw)
    if arr.ndim < 2:
        return None

    arr = np.squeeze(arr)
    if arr.ndim < 2:
        return None

    while arr.ndim > 2:
        # Prefer collapsing the smallest axis first:
        # (y, x, 1) -> squeeze to (y, x)
        # (frames, y, x) -> take first frame
        # (y, x, channels) -> take first channel
        axis = int(np.argmin(arr.shape))
        arr = np.take(arr, indices=0, axis=axis)

    return arr


def _normalize_to_uint8(raw):
    arr = np.asarray(raw)
    if arr.size == 0:
        return None
    norm = cv2.normalize(arr, None, 0, 255, cv2.NORM_MINMAX)
    return norm.astype(np.uint8)


def _iter_emd_image_groups(h5_file):
    """Yield candidate EMD image groups in Velox and Berkeley-style layouts."""
    if 'Data' in h5_file and 'Image' in h5_file['Data']:
        for key, grp in h5_file['Data']['Image'].items():
            if isinstance(grp, h5py.Group) and 'Data' in grp and isinstance(grp['Data'], h5py.Dataset):
                yield "velox", key, grp, 'Data'

    if 'data' in h5_file:
        for key, grp in h5_file['data'].items():
            if isinstance(grp, h5py.Group) and 'data' in grp and isinstance(grp['data'], h5py.Dataset):
                yield "berkeley", key, grp, 'data'


def _read_emd_metadata_text(group):
    dataset = group.get('Metadata')
    if not isinstance(dataset, h5py.Dataset):
        return None

    try:
        raw = bytes(np.asarray(dataset).reshape(-1).tolist())
    except Exception:
        return None

    text = raw.decode("utf-8", errors="ignore").strip("\x00 \n\r\t")
    return text or None


def _extract_emd_pixel_size_from_metadata_text(metadata_text):
    if not metadata_text:
        return None

    try:
        payload = json.loads(metadata_text)
    except json.JSONDecodeError:
        payload = None

    if payload is not None:
        stack = [payload]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                pixel_size = node.get("PixelSize")
                if isinstance(pixel_size, dict):
                    for axis_key, unit_key in (("width", "PixelUnitX"), ("height", "PixelUnitY"), ("x", "PixelUnitX"), ("y", "PixelUnitY")):
                        value = _coerce_float(pixel_size.get(axis_key))
                        unit = node.get(unit_key) or node.get("PixelUnit") or pixel_size.get("unit")
                        if value is not None and unit:
                            nm = _convert_to_nm(value, str(unit))
                            if nm and nm > 0:
                                return nm
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)

    match = re.search(
        r'"PixelSize"\s*:\s*\{[^{}]*"width"\s*:\s*"?(?P<value>[\d.eE+-]+)"?[^{}]*\}[^{}]*"PixelUnitX"\s*:\s*"(?P<unit>[^"]+)"',
        metadata_text,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        value = _coerce_float(match.group("value"))
        unit = match.group("unit")
        if value is not None:
            nm = _convert_to_nm(value, unit)
            if nm and nm > 0:
                return nm

    return None


def read_emd_pixel_size(image_path: Path):
    """Read pixel size from common EMD metadata layouts and Velox JSON metadata."""
    try:
        with h5py.File(str(image_path), 'r') as f:
            for fmt, key, grp, _ in _iter_emd_image_groups(f):
                if fmt == "velox":
                    pixel_size_group = grp.get('PixelSize')
                    if isinstance(pixel_size_group, h5py.Group):
                        width = _coerce_float(_normalize_h5_attr(pixel_size_group.attrs.get('width')))
                        unit = _normalize_h5_attr(pixel_size_group.attrs.get('unit', 'm'))
                        if width is not None:
                            nm = _convert_to_nm(width, str(unit))
                            if nm and nm > 0:
                                return nm

                    dimension_group = grp.get('Dimension')
                    if isinstance(dimension_group, h5py.Group):
                        for dim in dimension_group.values():
                            if not isinstance(dim, h5py.Dataset):
                                continue
                            scale = _coerce_float(_normalize_h5_attr(dim.attrs.get('Scale')))
                            unit = _normalize_h5_attr(dim.attrs.get('Unit', ''))
                            if scale is None or not unit:
                                continue
                            nm = _convert_to_nm(scale, str(unit))
                            if nm and nm > 0:
                                return nm

                    metadata_text = _read_emd_metadata_text(grp)
                    metadata_nm = _extract_emd_pixel_size_from_metadata_text(metadata_text)
                    if metadata_nm:
                        return metadata_nm

                if fmt == "berkeley":
                    dim1 = grp.get('dim1')
                    if isinstance(dim1, h5py.Dataset):
                        dim1_data = dim1[:]
                        if len(dim1_data) > 1:
                            delta = _coerce_float(dim1_data[1] - dim1_data[0])
                            if delta is not None and delta > 0:
                                return delta
    except Exception as e:
        print(f"Error reading EMD metadata: {e}")

    return None


def read_emd_image(image_path: Path):
    """Read and normalize the best available 2D image plane from an EMD file."""
    try:
        with h5py.File(str(image_path), 'r') as f:
            best_plane = None
            best_area = -1

            for _, _, grp, data_key in _iter_emd_image_groups(f):
                raw = grp[data_key][:]
                plane = _emd_dataset_to_2d(raw)
                if plane is None:
                    continue

                area = int(plane.shape[0]) * int(plane.shape[1])
                if area > best_area:
                    best_plane = plane
                    best_area = area

            if best_plane is not None:
                return _normalize_to_uint8(best_plane)
    except Exception as e:
        print(f"Error reading EMD image: {e}")

    return None


def _read_tiff_pixel_size(image_path):
    """
    Try all known methods to extract pixel size from a TIFF file.
    Returns (pixel_size_nm, method_string) or (None, None).
    """
    with tifffile.TiffFile(str(image_path)) as tif:

        # --- Method 1: ImageJ metadata ---
        meta = getattr(tif, 'imagej_metadata', None)
        if meta:
            # 1a. Direct 'spacing' + 'unit'
            if 'unit' in meta and 'spacing' in meta:
                spacing = float(meta['spacing'])
                nm = _convert_to_nm(spacing, meta['unit'])
                if nm is not None and nm > 0:
                    print(f"[TIFF scale] ImageJ spacing={spacing} {meta['unit']} → {nm} nm/px")
                    return nm, "metadata_imagej"

            # 1b. ImageJ 'info' string (often contains scale info as key=value pairs)
            info_str = meta.get('Info') or meta.get('info') or ''
            if info_str:
                # Try "Pixel Width = 0.245 nm" or "Scale = 0.5 um" patterns
                for pattern in [
                    r'pixel\s*(?:width|size)\s*[=:]\s*([\d.eE+-]+)\s*(nm|µm|um|mm|m)\b',
                    r'scale\s*[=:]\s*([\d.eE+-]+)\s*(nm|µm|um|mm|m)\b',
                ]:
                    m = re.search(pattern, info_str, re.IGNORECASE)
                    if m:
                        val = float(m.group(1))
                        nm = _convert_to_nm(val, m.group(2))
                        if nm and nm > 0:
                            print(f"[TIFF scale] ImageJ info field: {m.group(0)} → {nm} nm/px")
                            return nm, "metadata_imagej_info"

        # --- Method 2: OME-TIFF (XML in ImageDescription) ---
        if tif.pages:
            desc_tag = tif.pages[0].tags.get('ImageDescription')
            if desc_tag:
                desc = str(desc_tag.value)
                if desc.strip().startswith('<?xml') or '<OME' in desc:
                    try:
                        # Strip XML namespace for simpler parsing
                        desc_clean = re.sub(r'\sxmlns="[^"]+"', '', desc, count=1)
                        root = ET.fromstring(desc_clean)
                        # Look for <Pixels PhysicalSizeX="..." PhysicalSizeXUnit="...">
                        for elem in root.iter():
                            if 'Pixels' in elem.tag:
                                ps_x = elem.attrib.get('PhysicalSizeX')
                                ps_unit = elem.attrib.get('PhysicalSizeXUnit', 'µm')  # OME default is µm
                                if ps_x:
                                    val = float(ps_x)
                                    nm = _convert_to_nm(val, ps_unit)
                                    if nm and nm > 0:
                                        print(f"[TIFF scale] OME-TIFF PhysicalSizeX={ps_x} {ps_unit} → {nm} nm/px")
                                        return nm, "metadata_ome"
                    except ET.ParseError:
                        pass

        # --- Method 3: FEI / Thermo Fisher / DigitalMicrograph custom TIFF tags ---
        if tif.pages:
            page = tif.pages[0]
            for tag_id in (34682, 65027):
                fei_tag = page.tags.get(tag_id)
                if not fei_tag:
                    continue

                for fei_meta in _decode_tiff_tag_texts(fei_tag.value):
                    # Legacy FEI metadata stores PixelWidth in meters.
                    m = re.search(r'PixelWidth\s*=\s*([\d.eE+-]+)', fei_meta)
                    if m:
                        val_m = float(m.group(1))
                        nm = val_m * 1e9
                        if nm > 0:
                            print(f"[TIFF scale] FEI tag {tag_id} PixelWidth={val_m} m → {nm} nm/px")
                            return nm, f"metadata_fei_{tag_id}"

                    # DigitalMicrograph/JEOL headers often store PixelSizeX/Y as UTF-16-ish bytes.
                    for pattern in [
                        r'PixelSize(?:[XY])?[^0-9-]{0,80}(-?[\d.]+(?:e[-+]?\d+)?)\s*(nm|µm|um|mm|m)\b',
                        r'Pixel(?:Width|Height)(?:[XY])?[^0-9-]{0,80}(-?[\d.]+(?:e[-+]?\d+)?)\s*(nm|µm|um|mm|m)\b',
                    ]:
                        m = re.search(pattern, fei_meta, re.IGNORECASE | re.DOTALL)
                        if m:
                            val = float(m.group(1))
                            nm = _convert_to_nm(val, m.group(2))
                            if nm and nm > 0:
                                print(f"[TIFF scale] Private tag {tag_id}: {m.group(0)} → {nm} nm/px")
                                return nm, f"metadata_private_{tag_id}"

        # --- Method 4: ImageDescription free-text patterns ---
        if tif.pages:
            desc_tag = tif.pages[0].tags.get('ImageDescription')
            if desc_tag:
                desc = str(desc_tag.value)
                for pattern in [
                    r'pixel\s*size\s*[=:]\s*([\d.eE+-]+)\s*(nm|µm|um|mm|m)\b',
                    r'scale\s*[=:]\s*([\d.eE+-]+)\s*(nm|µm|um|mm|m)\b',
                    r'resolution\s*[=:]\s*([\d.eE+-]+)\s*(nm|µm|um|mm|m)\s*/\s*(?:pixel|px)',
                ]:
                    m = re.search(pattern, desc, re.IGNORECASE)
                    if m:
                        val = float(m.group(1))
                        nm = _convert_to_nm(val, m.group(2))
                        if nm and nm > 0:
                            print(f"[TIFF scale] ImageDescription: {m.group(0)} → {nm} nm/px")
                            return nm, "metadata_tiff_description"

        # --- Method 5: Standard TIFF resolution tags ---
        # CAUTION: most TIFFs have default 72 or 96 dpi, which is meaningless for microscopy.
        # Only use this if the result gives a plausible nm/pixel for TEM/SEM (0.01 ~ 100 nm/px).
        if tif.pages:
            page = tif.pages[0]
            tags = page.tags
            x_res_tag = tags.get('XResolution')
            res_unit_tag = tags.get('ResolutionUnit')
            if x_res_tag is not None:
                x_res_val = x_res_tag.value
                pixels_per_unit = None
                if isinstance(x_res_val, tuple) and len(x_res_val) == 2 and x_res_val[0] > 0:
                    pixels_per_unit = x_res_val[0] / x_res_val[1]
                elif isinstance(x_res_val, (int, float)) and x_res_val > 0:
                    pixels_per_unit = float(x_res_val)

                if pixels_per_unit and pixels_per_unit > 0:
                    res_unit = res_unit_tag.value if res_unit_tag else 1
                    nm_per_px = None
                    if res_unit == 3:  # centimeter
                        nm_per_px = 1e7 / pixels_per_unit
                    elif res_unit == 2:  # inch
                        nm_per_px = 2.54e7 / pixels_per_unit

                    # Only trust if result is in plausible microscopy range
                    if nm_per_px is not None and 0.01 <= nm_per_px <= 1000:
                        print(f"[TIFF scale] Resolution tag: {pixels_per_unit} px/unit (unit={res_unit}) → {nm_per_px} nm/px")
                        return nm_per_px, "metadata_tiff_resolution"
                    elif nm_per_px is not None:
                        print(f"[TIFF scale] Resolution tag gives {nm_per_px} nm/px — outside plausible range, ignoring (likely default DPI)")

        # --- Method 6: Check all TIFF tags for anything scale-related ---
        if tif.pages:
            for tag in tif.pages[0].tags.values():
                for tag_str in _decode_tiff_tag_texts(tag.value):
                    if len(tag_str) > 20000:
                        continue  # skip huge binary blobs
                    for pattern in [
                        r'(?:pixel|image)\s*(?:width|size|scale|resolution)\s*[=:]\s*([\d.eE+-]+)\s*(nm|µm|um|mm|m)\b',
                        r'(?:pixel|image)\s*(?:width|size|scale|resolution)[^0-9-]{0,80}(-?[\d.]+(?:e[-+]?\d+)?)\s*(nm|µm|um|mm|m)\b',
                    ]:
                        m = re.search(pattern, tag_str, re.IGNORECASE | re.DOTALL)
                        if m:
                            val = float(m.group(1))
                            nm = _convert_to_nm(val, m.group(2))
                            if nm and nm > 0:
                                print(f"[TIFF scale] Tag {tag.name}: {m.group(0)} → {nm} nm/px")
                                return nm, f"metadata_tiff_tag_{tag.name}"

    return None, None


def get_pixel_size(image_path: Path):
    """
    Extract pixel size (nm/pixel) from image metadata or scale bar.
    Returns a tuple: (pixel_size_nm, calibration_info)
    calibration_info is a dict with details for visualization (e.g., scale bar coordinates).
    """
    ext = image_path.suffix.lower()
    pixel_size = None
    method = "unknown"
    scale_bar_coords = None  # (x1, y1, x2, y2)
    scale_bar_length_nm = None
    best_line_width_px = None

    # 1. Try Metadata
    try:
        if ext in ['.dm3', '.dm4']:
            dm = nio.read(str(image_path))
            if 'pixelSize' in dm:
                pixel_size = dm['pixelSize'][0]
                method = "metadata_dm"
                print(f"[Scale] DM metadata: {pixel_size} nm/px")

        elif ext == '.emd':
            pixel_size = read_emd_pixel_size(image_path)
            if pixel_size is not None:
                method = "metadata_emd"

        elif ext in ['.tif', '.tiff']:
            pixel_size, method = _read_tiff_pixel_size(image_path)
            if pixel_size is None:
                method = "unknown"

    except Exception as e:
        print(f"Error extracting metadata: {e}")
        import traceback
        traceback.print_exc()

    # 2. Fallback: Scale Bar Detection (OCR + Line Detection)
    detected_pixel_size = None
    try:
        if ext == '.emd':
            img = read_emd_image(image_path)
        else:
            img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        if img is not None:
            h, w = img.shape

            # Scale bars are usually at the bottom
            bottom_crop = img[int(h * 0.8):, :]

            # Try both white-on-dark and dark-on-white scale bars
            _, thresh_white = cv2.threshold(bottom_crop, 200, 255, cv2.THRESH_BINARY)
            _, thresh_dark = cv2.threshold(bottom_crop, 50, 255, cv2.THRESH_BINARY_INV)

            for thresh in [thresh_white, thresh_dark]:
                contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                best_line_width_px = 0
                best_line_rect = None

                for cnt in contours:
                    x, y, cw, ch = cv2.boundingRect(cnt)
                    # Scale bar line is usually wide and thin
                    if cw > 50 and ch < 20:
                        if cw > best_line_width_px:
                            best_line_width_px = cw
                            best_line_rect = (x, y + int(h * 0.8), cw, ch)

                if best_line_rect:
                    lx, ly, lw, lh = best_line_rect
                    scale_bar_coords = (lx, ly + lh // 2, lx + lw, ly + lh // 2)

                    # OCR on the bottom area
                    pil_img = Image.fromarray(bottom_crop)
                    text = pytesseract.image_to_string(pil_img)
                    print(f"[Scale] OCR text from bottom crop: '{text.strip()}'")

                    # Parse: "200 nm", "1 µm", "500nm", "2 um", etc.
                    match = re.search(r'([\d.]+)\s*(nm|µm|um|μm)', text, re.IGNORECASE)
                    if match:
                        value = float(match.group(1))
                        unit = match.group(2)
                        scale_bar_length_nm = _convert_to_nm(value, unit)
                        if scale_bar_length_nm and best_line_width_px > 0:
                            detected_pixel_size = scale_bar_length_nm / best_line_width_px
                            print(f"[Scale] OCR: {value} {unit} over {best_line_width_px}px → {detected_pixel_size:.4f} nm/px")

                            if pixel_size is None:
                                pixel_size = detected_pixel_size
                                method = "ocr_scale_bar"
                    break  # found a scale bar line, stop trying thresholds

    except Exception as e:
        print(f"Error in scale bar detection: {e}")

    if pixel_size is None:
        method = "uncalibrated"
        print(f"[Scale] No calibration found for {image_path.name}")
    else:
        print(f"[Scale] Final: {pixel_size} nm/px via {method}")

    calibration_info = {
        "method": method,
        "scale_bar_coords": scale_bar_coords,
        "scale_bar_length_nm": scale_bar_length_nm,
        "scale_bar_length_px": best_line_width_px if scale_bar_coords else None
    }
    if pixel_size is None:
        calibration_info["warning"] = "No calibration found. Measurements are using a placeholder scale until you calibrate manually."

    return pixel_size, calibration_info
