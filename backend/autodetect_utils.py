import numpy as np
import cv2
import numpy as np
import cv2
from skimage import io, color, util, morphology, measure, filters, exposure, segmentation
from scipy import ndimage as ndi

def image_kmeans(image, k=2, separation_strength=0):
    """
    Segments the image using K-means clustering.
    Matches MATLAB 'imagekmeans.m' and 'loadEMimages.m' logic.
    """
    # 1. Preprocessing — Contrast Stretching
    p1, p99 = np.percentile(image, (1, 99))
    image_adj = exposure.rescale_intensity(image, in_range=(p1, p99), out_range=np.uint8)

    # 2. K-means clustering (k=2: foreground vs background)
    data = image_adj.reshape((-1, 1)).astype(np.float32)
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    flags = cv2.KMEANS_RANDOM_CENTERS
    compactness, labels, centers = cv2.kmeans(data, k, None, criteria, 10, flags)
    segmented_image = labels.reshape(image.shape)

    # 3. Foreground Selection — border-pixel voting
    # Border pixels are almost always background in microscopy images.
    # The cluster that dominates the border is background; the other is foreground.
    # This works for BOTH black-bg (bright particles) and white-bg (dark particles).
    h, w = image_adj.shape[:2]
    border_labels = np.concatenate([
        segmented_image[0, :],        # top row
        segmented_image[h-1, :],      # bottom row
        segmented_image[1:h-1, 0],    # left column
        segmented_image[1:h-1, w-1]   # right column
    ])
    # Majority vote: which cluster appears more on the border?
    bg_cluster = int(np.round(np.mean(border_labels)))
    fg_cluster = 1 - bg_cluster

    binary = (segmented_image == fg_cluster)

    # 4. Post-processing (Morphology chain from imagekmeans.m)
    # NOTE: Border objects are filtered per-particle in processing.py, not here
    # BW_fill_filter = imfill(BW,4,'holes');
    binary = ndi.binary_fill_holes(binary)
    
    # BW_fill_filter = bwareafilt(BW_fill_filter, [500 5000000]);
    # Remove small objects (noise)
    binary = morphology.remove_small_objects(binary, min_size=500)
    
    # BW_fill_filter = bwmorph(BW_fill_filter,'spur'); -> Skip (minor)
    # BW_fill_filter = bwmorph(BW_fill_filter,'majority');
    # Majority: pixel is white if >=5 of 3x3 neighbors are white
    # We can use rank filter or just skip if subtle. 
    # Let's Skip majority to avoid rounding corners too much.
    
    # Allow a user-controlled separation/merge bias.
    # Positive values favor splitting lightly connected regions.
    # Negative values favor keeping nearby regions connected.
    # Use a nonlinear radius map so upper slider values feel meaningfully stronger.
    separation_strength = int(np.clip(separation_strength, -6, 6))
    radius_by_strength = [1, 3, 6, 9, 13, 17, 22]
    closing_radius = radius_by_strength[max(0, -separation_strength)]
    opening_radius = radius_by_strength[max(0, separation_strength)]

    # BW_fill_filter = bwmorph(BW_fill_filter,'close');
    binary = morphology.binary_closing(binary, morphology.disk(closing_radius))
    
    # BW_fill_filter = bwmorph(BW_fill_filter,'bridge'); 
    # Bridge unconnected pixels. Closing roughly does this.
    
    # BW_fill_filter = bwmorph(BW_fill_filter,'open');
    binary = morphology.binary_opening(binary, morphology.disk(opening_radius))
    
    # BW_fill_filter = imfill(BW_fill_filter,4,'holes');
    binary = ndi.binary_fill_holes(binary)
    
    # BW_fill_filter = imfilter(..., gaussian) -> Skipped as it returns float, we need binary.
    
    return binary.astype(np.uint8)

def compute_hu_moments(image):
    """
    Computes Hu moments for a binary or grayscale image.
    """
    moments = measure.moments_central(image)
    hu_moments = measure.moments_hu(moments)
    return hu_moments

def masking(img, region_coords):
    """
    Helper function to create a masked image from region coordinates.
    """
    mask = np.zeros(img.shape, dtype=bool)
    # region_coords is (N, 2) array of (row, col)
    mask[region_coords[:, 0], region_coords[:, 1]] = True
    return img & mask

def ruecs(img_input, area_threshold=25, cnt=0):
    """
    Recursive Ultimate Erosion of Convex Shapes (rUECS).
    
    Args:
        img_input: Binary image (numpy array) or a list of dictionaries representing particles.
        area_threshold: Minimum area to keep.
        cnt: Iteration counter (used in recursion).
    """
    
    # Initialize if input is an image
    if not isinstance(img_input, list):
        img_bool = img_input > 0
        area = np.sum(img_bool)
        
        particle = {
            'image': img_bool,
            'init_area': area,
            'area': area,
            'cnt': cnt,
            'isconvex': False,
            'keep': True
        }
        img_list = [particle]
    else:
        img_list = img_input

    # Structuring elements
    se1 = morphology.disk(1)
    se2 = np.ones((2, 2), dtype=np.uint8)
    
    queue = list(img_list)
    final_markers = []
    
    while queue:
        current_particle = queue.pop(0)
        
        if not current_particle['keep']:
            final_markers.append(current_particle)
            continue
            
        if current_particle['isconvex']:
            final_markers.append(current_particle)
            continue
            
        image = current_particle['image']
        
        # Check if empty
        if not np.any(image):
            current_particle['keep'] = False
            final_markers.append(current_particle)
            continue

        # Label to handle connected components
        label_img = measure.label(image)
        if np.max(label_img) == 0:
             current_particle['keep'] = False
             final_markers.append(current_particle)
             continue
             
        regions = measure.regionprops(label_img)
        # Assuming single object or taking the first major one
        s = regions[0] 
        
        # Convexity criteria
        # Solidity = Area / ConvexArea
        # Defect = 1 - Solidity
        # Original: (1 - Area/ConvexArea > 0.1) -> Solidity < 0.9
        
        is_convex = True
        if s.area_convex == 0:
            convexity_defect = 0
        else:
            convexity_defect = 1.0 - (s.area / s.area_convex)
        
        # Perimeter ratio check (approx)
        # Using convex_image perimeter
        ch_perimeter = 0
        if s.image_convex.ndim == 2:
             ch_perimeter = measure.perimeter(s.image_convex)
        
        perimeter_ratio = 0
        if s.perimeter > 0:
            perimeter_ratio = ch_perimeter / s.perimeter
        
        if (convexity_defect > 0.1) or (perimeter_ratio < 0.9):
            is_convex = False
            
        if not is_convex:
            # Erode
            if current_particle['cnt'] % 2 == 1:
                se = se1
            else:
                se = se2
                
            eroded = morphology.erosion(image, se)
            opened = morphology.opening(eroded, se1)
            
            if not np.any(opened):
                current_particle['keep'] = False
                final_markers.append(current_particle)
                continue
                
            label_eroded = measure.label(opened)
            regions_eroded = measure.regionprops(label_eroded)
            
            if not regions_eroded:
                current_particle['keep'] = False
                final_markers.append(current_particle)
                continue
                
            first_region = regions_eroded[0]
            
            # Update current particle
            current_particle['image'] = masking(opened, first_region.coords)
            current_particle['cnt'] += 1
            current_particle['area'] = first_region.area
            
            # Check area threshold
            if (current_particle['area'] < 0.1 * current_particle['init_area']) or (current_particle['area'] < area_threshold):
                current_particle['keep'] = False
            
            # Split case
            if len(regions_eroded) > 1:
                current_particle['init_area'] = first_region.area
                queue.insert(0, current_particle) 
                
                for i in range(1, len(regions_eroded)):
                    sub_region = regions_eroded[i]
                    sub_img = masking(opened, sub_region.coords)
                    
                    new_particle = {
                        'image': sub_img,
                        'init_area': sub_region.area,
                        'area': sub_region.area,
                        'cnt': current_particle['cnt'],
                        'isconvex': False,
                        'keep': True
                    }
                    
                    # Recurse
                    sub_markers = ruecs([new_particle], area_threshold, current_particle['cnt'])
                    queue.extend(sub_markers)

            else:
                queue.insert(0, current_particle)
                
        else:
            current_particle['isconvex'] = True
            final_markers.append(current_particle)

    # Final filtering
    filtered_markers = []
    for m in final_markers:
        if m['area'] < area_threshold:
            m['keep'] = False
        if m['keep']:
            filtered_markers.append(m)
            
    return filtered_markers

def dilmarkers(markers, original_shape):
    """
    Dilates markers back to their original size.
    Returns: dilated_markers (list), overlay (RGB)
    """
    if not markers:
        # handle case where original_shape might be image or tuple
        shape = original_shape if isinstance(original_shape, tuple) else original_shape.shape[:2]
        return [], np.zeros(shape + (3,), dtype=np.uint8)
        
    se1 = morphology.disk(1)
    se2 = np.ones((2, 2), dtype=np.uint8)
    
    dilated_markers = []
    
    # Determine shape
    if isinstance(original_shape, np.ndarray):
        bg_image = original_shape
        if bg_image.ndim == 2:
            bg_image = color.gray2rgb(bg_image)
        elif bg_image.shape[2] == 4:
            bg_image = color.rgba2rgb(bg_image)
        if bg_image.dtype != np.uint8:
            bg_image = util.img_as_ubyte(bg_image)
        image_shape = bg_image.shape[:2]
    else:
        image_shape = original_shape
        bg_image = np.zeros(image_shape + (3,), dtype=np.uint8)

    for marker in markers:
        m_img = marker['image']
        cnt = marker['cnt']
        
        # Dilate
        dilated = m_img.copy()
        for j in range(cnt, 0, -1):
            if j % 2 == 1:
                se = se1
            else:
                se = se2
                
            # Keep dilation constrained to the image size (it is same size masks)
            dilated = morphology.binary_dilation(dilated, se)
            
        dilated_markers.append(dilated)
        
    # We mainly need the dilated markers list
    # Constructing overlay omitted for speed unless needed, but returning dummy if needed
    # The user code might check return tuple.
    
    return dilated_markers, bg_image # returning image as overlay placeholder
