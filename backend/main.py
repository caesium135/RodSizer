from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import shutil
import os
import uuid
import glob
from pathlib import Path
from typing import List
from processing import process_image, generate_preview, save_results_to_excel
from typing import Optional
from pydantic import BaseModel
import json

class ExportRequest(BaseModel):
    image_id: str
    selected_ids: List[int]
    
app = FastAPI(title="Gold Nanorod Detector")


# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Directories
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
RESULTS_DIR = BASE_DIR / "results"
FRONTEND_DIR = BASE_DIR / "frontend"

UPLOAD_DIR.mkdir(exist_ok=True)
RESULTS_DIR.mkdir(exist_ok=True)
FRONTEND_DIR.mkdir(exist_ok=True)

# Serve Frontend
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

@app.get("/")
async def read_index():
    return FileResponse(FRONTEND_DIR / "index.html")

@app.get("/analysis")
async def read_analysis():
    return FileResponse(FRONTEND_DIR / "analysis.html")

@app.get("/folder_analysis")
async def read_folder_analysis():
    return FileResponse(FRONTEND_DIR / "folder_analysis.html")

# --- Folder Management ---

@app.post("/folders")
async def create_folder(folder_name: str = Form(...)):
    try:
        # Sanitize folder name (basic)
        safe_name = "".join([c for c in folder_name if c.isalnum() or c in " -_"]).strip()
        if not safe_name:
             raise HTTPException(status_code=400, detail="Invalid folder name")
        
        folder_path = UPLOAD_DIR / safe_name
        if folder_path.exists():
             raise HTTPException(status_code=400, detail="Folder already exists")
        
        folder_path.mkdir(parents=True, exist_ok=True)
        return {"status": "success", "folder": safe_name}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/folders")
async def list_folders():
    folders = []
    # Ensure root exists
    if not UPLOAD_DIR.exists():
        return []
    
    for path in UPLOAD_DIR.iterdir():
        if path.is_dir():
            folders.append(path.name)
    folders.sort()
    return folders

@app.delete("/folders/{folder_name}")
async def delete_folder(folder_name: str):
    try:
        folder_path = UPLOAD_DIR / folder_name
        if not folder_path.exists() or not folder_path.is_dir():
            raise HTTPException(status_code=404, detail="Folder not found")
        
        # Delete folder and contents
        shutil.rmtree(folder_path)
        
        # Also clean up results for images that were in this folder?
        # Since we don't strictly track which result belongs to which folder in the filename (only ID),
        # this is tricky unless we scan the deleted files.
        # For now, let's just delete the upload folder. Orphaned results are harmless but take space.
        
        return {"status": "success", "message": "Folder deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- Folder Aggregation ---

class FolderSelectionRequest(BaseModel):
    image_id: str
    selected_ids: List[int]

@app.post("/folders/{folder_name}/save_selection")
async def save_folder_selection(folder_name: str, req: FolderSelectionRequest):
    try:
        folder_path = UPLOAD_DIR / folder_name
        if not folder_path.exists():
            raise HTTPException(status_code=404, detail="Folder not found")
            
        # Analysis cache dir inside the folder (hidden)
        cache_dir = folder_path / ".analysis_cache"
        cache_dir.mkdir(exist_ok=True)
        
        # Load original full results
        json_path = RESULTS_DIR / f"{req.image_id}_results.json"
        if not json_path.exists():
             raise HTTPException(status_code=404, detail="Original analysis not found")
             
        with open(json_path) as f:
            data = json.load(f)
            
        # Filter
        full_results = data.get("data", [])
        filtered = [r for r in full_results if r["id"] in req.selected_ids]
        
        if not filtered:
             raise HTTPException(status_code=400, detail="No particles selected to save")
             
        # Save payload
        save_payload = {
            "image_id": req.image_id,
            "filename": data.get("filename", req.image_id),
            "data": filtered,
            "timestamp": data.get("timestamp", ""), # if available
            "pixel_size_nm": data.get("pixel_size_nm", 0)
        }
        
        output_path = cache_dir / f"{req.image_id}.json"
        with open(output_path, "w") as f:
            json.dump(save_payload, f, indent=2)
            
        return {"status": "success", "count": len(filtered)}
        
    except Exception as e:
        print(f"Save Selection Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/folders/{folder_name}/aggregate")
async def aggregate_folder(folder_name: str):
    try:
        folder_path = UPLOAD_DIR / folder_name
        cache_dir = folder_path / ".analysis_cache"
        
        if not cache_dir.exists():
            return {"data": [], "stats": {}, "file_count": 0}
            
        combined_data = []
        files = list(cache_dir.glob("*.json"))
        
        for p in files:
            with open(p) as f:
                payload = json.load(f)
                fname = payload.get("filename", "unknown")
                # Append source info to each particle
                for p_data in payload.get("data", []):
                    p_data["source_image"] = fname
                    combined_data.append(p_data)
                    
        # Calculate Aggregated Stats
        stats = {}
        if combined_data:
            # We can use pandas for quick stats if available or manual
            # Let's use pandas since we used it in processing
            import pandas as pd
            df = pd.DataFrame(combined_data)
            
            # Helper
            def get_stat(col):
                if col not in df: return 0
                return round(float(df[col].mean()), 1), round(float(df[col].std()), 1)
            
            l_m, l_s = get_stat("length_nm")
            w_m, w_s = get_stat("width_nm")
            ar_m, ar_s = get_stat("aspect_ratio")
            
            stats = {
                "count": len(combined_data),
                "mean_length": f"{l_m} ± {l_s}",
                "mean_width": f"{w_m} ± {w_s}",
                "mean_ar": f"{ar_m} ± {ar_s}"
            }

        return {
            "data": combined_data,
            "stats": stats,
            "file_count": len(files)
        }

    except Exception as e:
        print(f"Aggregate Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/folders/{folder_name}/export_aggregate")
async def export_aggregate_folder(folder_name: str):
    try:
        folder_path = UPLOAD_DIR / folder_name
        cache_dir = folder_path / ".analysis_cache"
        
        if not cache_dir.exists():
            raise HTTPException(status_code=404, detail="No data to export")
            
        combined_data = []
        files = list(cache_dir.glob("*.json"))
        
        for p in files:
            with open(p) as f:
                payload = json.load(f)
                fname = payload.get("filename", "unknown")
                # Append source info to each particle
                for p_data in payload.get("data", []):
                    p_data["source_image"] = fname
                    combined_data.append(p_data)
        
        if not combined_data:
            raise HTTPException(status_code=400, detail="No data found")

        # Generate Temp Excel
        temp_name = f"export_folder_{folder_name}_{uuid.uuid4().hex[:8]}.xlsx"
        temp_path = RESULTS_DIR / temp_name
        
        save_results_to_excel(combined_data, temp_path)
        
        return FileResponse(
            path=temp_path, 
            filename=f"{folder_name}_analysis_report.xlsx",
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"Export Aggregate Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# -------------------------

@app.post("/upload")
async def upload_images(background_tasks: BackgroundTasks, folder: str = Form(None), files: List[UploadFile] = File(...)):
    uploaded_files = []
    try:
        for file in files:
            file_id = str(uuid.uuid4())
            safe_filename = Path(file.filename).name
            save_name = f"{file_id}_{safe_filename}"
            
            # Determine save directory
            if folder:
                save_dir = UPLOAD_DIR / folder
                if not save_dir.exists():
                    raise HTTPException(status_code=400, detail="Folder does not exist")
            else:
                save_dir = UPLOAD_DIR
                
            file_path = save_dir / save_name
            
            with open(file_path, "wb") as buffer:
                shutil.copyfileobj(file.file, buffer)
            
            # 1. Generate Immediate Preview (Sync)
            # This ensures the user sees something right away
            generate_preview(file_path, RESULTS_DIR)
            
            uploaded_files.append({
                "id": file_path.stem, 
                "filename": safe_filename,
                "status": "processing"
            })
            
            # 2. Queue Heavy Processing (Background)
            # Find matching calibration file (.dm3/.dm4)
            search_dir = file_path.parent
            calibration_source_path = None
            original_stem = None
            
            if len(save_name) > 37 and save_name[36] == '_':
                original_stem = Path(save_name[37:]).stem
            else:
                original_stem = Path(save_name).stem
                
            for f in search_dir.glob("*"):
                if f.suffix.lower() in ['.dm3', '.dm4']:
                    dm3_stem = None
                    if len(f.name) > 37 and f.name[36] == '_':
                        dm3_stem = Path(f.name[37:]).stem
                    else:
                        dm3_stem = f.stem
                    if dm3_stem == original_stem:
                        calibration_source_path = f
                        break
            
            # Add to background tasks
            background_tasks.add_task(process_image, file_path, RESULTS_DIR, None, calibration_source_path)

        return uploaded_files
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/images")
async def list_images(folder: str = Query(None)):
    images = []
    
    target_dir = UPLOAD_DIR
    if folder:
        target_dir = UPLOAD_DIR / folder
        if not target_dir.exists():
            return [] # Empty if folder doesn't exist
            
    for path in target_dir.glob("*"):
        if path.is_file() and path.suffix.lower() in ['.tif', '.tiff', '.jpg', '.jpeg', '.png', '.dm3', '.dm4']:
            # Try to extract original name if it follows UUID_Name pattern
            display_name = path.name
            if len(path.name) > 37 and path.name[36] == '_':
                display_name = path.name[37:]
            
            # Check status
            image_id = path.stem
            # If overlay exists, it's done
            overlay_path = RESULTS_DIR / f"{image_id}_overlay.jpg"
            status = "complete" if overlay_path.exists() else "processing"
            
            images.append({
                "id": image_id, 
                "filename": path.name,
                "display_name": display_name,
                "status": status
            })
    # Sort by newest first (optional, but nice)
    images.sort(key=lambda x: x['display_name'])
    return images

@app.delete("/images/{image_id}")
async def delete_image(image_id: str):
    try:
        # Find file in uploads (recursive search)
        files = list(UPLOAD_DIR.rglob(f"{image_id}.*"))
        if not files:
            raise HTTPException(status_code=404, detail="Image not found")
        
        # Delete source file
        for f in files:
            os.remove(f)
            
        # Delete results if they exist
        # Result files usually start with image_id
        for res_file in RESULTS_DIR.glob(f"{image_id}*"):
            os.remove(res_file)
            
        return {"status": "success", "message": "Image deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/process/{image_id}")
async def process_image_endpoint(image_id: str, manual_pixel_size: float = None, requested_bar_length_nm: float = None):
    try:
        # Find file with image_id (recursive search for subfolders)
        files = list(UPLOAD_DIR.rglob(f"{image_id}.*"))
        if not files:
            raise HTTPException(status_code=404, detail="Image not found")
        
        input_path = files[0]
        search_dir = input_path.parent
        
        # Try to find a matching .dm3 file for calibration
        calibration_source_path = None
        
        # Extract original filename stem (removing UUID prefix if present)
        current_filename = input_path.name
        original_stem = None
        
        if len(current_filename) > 37 and current_filename[36] == '_':
            original_name_with_ext = current_filename[37:]
            original_stem = Path(original_name_with_ext).stem
        else:
            original_stem = input_path.stem

        # Search for .dm3/.dm4 files in the SAME directory
        if original_stem:
            for f in search_dir.glob("*"):
                if f.suffix.lower() in ['.dm3', '.dm4']:
                    dm3_stem = None
                    if len(f.name) > 37 and f.name[36] == '_':
                        dm3_stem = Path(f.name[37:]).stem
                    else:
                        dm3_stem = f.stem
                    
                    if dm3_stem == original_stem:
                        calibration_source_path = f
                        break
        
        if not manual_pixel_size:
            # Check for existing results to avoid re-processing
            results_path = RESULTS_DIR / f"{image_id}_results.json"
            if results_path.exists():
                import json
                try:
                    with open(results_path, 'r') as f:
                        return json.load(f)
                except Exception:
                    pass # If corrupt, re-process

        result = process_image(input_path, RESULTS_DIR, manual_pixel_size, calibration_source_path)
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/results/{filename}")
async def get_result_file(filename: str):
    file_path = RESULTS_DIR / filename
    if not file_path.exists():
        # Try looking in uploads for original images if requested via this endpoint
        # Check root
        file_path = UPLOAD_DIR / filename
        if not file_path.exists():
            # Check recursively in uploads
            found = list(UPLOAD_DIR.rglob(filename))
            if found:
                file_path = found[0]
            else:
                raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)

# --- Export ---

@app.post("/export")
async def export_data(req: ExportRequest):
    try:
        # Load cache
        json_path = RESULTS_DIR / f"{req.image_id}_results.json"
        if not json_path.exists():
            raise HTTPException(status_code=404, detail="Results not found")
            
        with open(json_path) as f:
            data = json.load(f)
            
        full_results = data.get("data", [])
        
        # Filter Logic
        # If selected_ids is empty, interpret as "None Selected" -> Empty file?
        # Or strict adherence: Only export what is in list.
        # Frontend ensures at least one is selected ideally, or we export empty.
        
        filtered_results = [r for r in full_results if r["id"] in req.selected_ids]
        
        if not filtered_results:
             raise HTTPException(status_code=400, detail="No particles selected")

        # Generate Temp Excel
        temp_name = f"export_{req.image_id}_{uuid.uuid4().hex[:8]}.xlsx"
        temp_path = RESULTS_DIR / temp_name
        
        save_results_to_excel(filtered_results, temp_path)
        
        # We should use BackgroundTasks to clean up, but simpler here:
        # FileResponse can delete after? using background. 
        # But allow it to persist is fine for now (results dir is cache).
        
        original_filename = data.get("filename", req.image_id)
        # Ensure it's safe? It was sanitized in processing.py.
        
        return FileResponse(
            path=temp_path, 
            filename=f"{original_filename}_detected.xlsx",
            media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        print(f"Export Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
