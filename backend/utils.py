from pathlib import Path
import ncempy.io as nio
import tifffile
import cv2
import numpy as np
import pytesseract
import re
from PIL import Image

def get_pixel_size(image_path: Path):
    """
    Extract pixel size (nm/pixel) from image metadata or scale bar.
    Returns a tuple: (pixel_size_nm, calibration_info)
    calibration_info is a dict with details for visualization (e.g., scale bar coordinates).
    """
    ext = image_path.suffix.lower()
    pixel_size = None
    method = "unknown"
    scale_bar_coords = None # (x1, y1, x2, y2)
    scale_bar_length_nm = None

    # 1. Try Metadata (ncempy / tifffile)
    try:
        if ext in ['.dm3', '.dm4']:
            dm = nio.read(str(image_path))
            if 'pixelSize' in dm:
                 pixel_size = dm['pixelSize'][0]
                 method = "metadata_dm"
            
        elif ext in ['.tif', '.tiff']:
            with tifffile.TiffFile(str(image_path)) as tif:
                # Check for common tags
                # ImageJ tags often store pixel size
                if hasattr(tif, 'imagej_metadata'):
                    meta = tif.imagej_metadata
                    if meta and 'unit' in meta and 'spacing' in meta:
                        if meta['unit'] in ['nm', 'nanometer']:
                            pixel_size = meta['spacing']
                            method = "metadata_imagej"
                
                # Check standard resolution tags (ResolutionUnit: 2=inch, 3=cm)
                # Often not useful for TEM unless specifically set
                pass
                
    except Exception as e:
        print(f"Error extracting metadata: {e}")

    # 2. Fallback: Scale Bar Detection (OCR + Line Detection)
    # Even if metadata found, we might want to detect scale bar for verification if requested
    # But priority is metadata if available and reliable.
    # User requested visual verification, so let's try to find the scale bar anyway.
    
    detected_pixel_size = None
    try:
        img = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
        h, w = img.shape
        
        # Scale bars are usually at the bottom, white text and line
        bottom_crop = img[int(h*0.8):, :]
        
        # Threshold to find white features
        # Lowered to 200 to catch anti-aliased text/lines
        _, thresh = cv2.threshold(bottom_crop, 200, 255, cv2.THRESH_BINARY)
        
        # Find lines (scale bar line)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        
        best_line_width_px = 0
        best_line_rect = None
        
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            # Scale bar line is usually wide and thin
            if cw > 50 and ch < 20: 
                if cw > best_line_width_px:
                    best_line_width_px = cw
                    best_line_rect = (x, y + int(h*0.8), cw, ch)
        
        if best_line_rect:
            # Look for text near the line
            # ROI for text: slightly above or below or next to line
            # Usually text is above the line in Gatan
            lx, ly, lw, lh = best_line_rect
            scale_bar_coords = (lx, ly + lh//2, lx + lw, ly + lh//2)
            
            # OCR on the bottom area
            # Use PIL for OCR
            pil_img = Image.fromarray(bottom_crop)
            text = pytesseract.image_to_string(pil_img)
            
            # Parse text for number and unit (e.g., "200 nm")
            # Regex to find number followed by nm
            match = re.search(r'(\d+)\s*nm', text, re.IGNORECASE)
            if match:
                scale_bar_length_nm = float(match.group(1))
                detected_pixel_size = scale_bar_length_nm / best_line_width_px
                
                if pixel_size is None:
                    pixel_size = detected_pixel_size
                    method = "ocr_scale_bar"
            
    except Exception as e:
        print(f"Error in scale bar detection: {e}")

    # Default fallback
    if pixel_size is None:
        pixel_size = 1.0
        method = "default"

    return pixel_size, {
        "method": method,
        "scale_bar_coords": scale_bar_coords, # [x1, y1, x2, y2]
        "scale_bar_length_nm": scale_bar_length_nm,
        "scale_bar_length_px": best_line_width_px if scale_bar_coords else None
    }
