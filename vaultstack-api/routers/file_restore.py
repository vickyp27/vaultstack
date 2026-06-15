from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List
import uuid, os
from database import get_db
from models.backup import BackupJob

router = APIRouter(prefix="/api/v1/file-restore", tags=["file-restore"])


class BrowseRequest(BaseModel):
    path: str = "/"


class ExtractRequest(BaseModel):
    paths: List[str]


def _celery():
    from celery_app import app
    return app


@router.post("/{backup_id}/browse")
def browse(backup_id: str, req: BrowseRequest, db: Session = Depends(get_db)):
    job = db.query(BackupJob).filter(BackupJob.id == uuid.UUID(backup_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Backup not found")
    if job.status != "success" or not job.backup_path:
        raise HTTPException(status_code=400, detail="Backup not available for file restore")

    result = _celery().send_task(
        "tasks.file_restore_task.browse_backup",
        args=[backup_id, req.path],
    )
    try:
        return result.get(timeout=180)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{backup_id}/download")
def download_files(backup_id: str, req: ExtractRequest, db: Session = Depends(get_db)):
    if not req.paths:
        raise HTTPException(status_code=400, detail="No files selected")

    job = db.query(BackupJob).filter(BackupJob.id == uuid.UUID(backup_id)).first()
    if not job:
        raise HTTPException(status_code=404, detail="Backup not found")
    if job.status != "success" or not job.backup_path:
        raise HTTPException(status_code=400, detail="Backup not available for file restore")

    result = _celery().send_task(
        "tasks.file_restore_task.extract_files",
        args=[backup_id, req.paths],
    )
    try:
        data = result.get(timeout=300)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    zip_path = data.get("zip_path")
    if not zip_path or not os.path.exists(zip_path):
        raise HTTPException(status_code=500, detail="Extraction failed — zip not found")

    vm_name = (data.get("vm_name") or "backup").replace(" ", "_")
    filename = f"{vm_name}_files.zip"

    def stream_and_cleanup():
        try:
            with open(zip_path, "rb") as f:
                while chunk := f.read(65536):
                    yield chunk
        finally:
            try:
                os.unlink(zip_path)
            except Exception:
                pass

    return StreamingResponse(
        stream_and_cleanup(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
