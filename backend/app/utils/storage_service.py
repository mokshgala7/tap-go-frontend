import uuid
import os
import mimetypes
from typing import Optional
from fastapi import UploadFile, HTTPException, status
from supabase import create_client, Client
from app.config import settings

# Initialize Supabase client using Service Role Key to bypass RLS for server-side uploads
_supabase: Optional[Client] = None
if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_ROLE_KEY:
    _supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_ROLE_KEY)

MAX_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_EXTENSIONS = [".jpg", ".jpeg", ".png", ".pdf"]
ALLOWED_IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png"]

def upload_document(file: UploadFile, folder: str, allowed_extensions: list = None) -> Optional[str]:
    """
    Uploads a file to the configured private Supabase Storage bucket.
    Returns the canonical object path (e.g., 'folder/uuid.ext') or raises HTTPException.
    """
    if not file or not file.filename:
        return None

    if not _supabase:
        # In a real environment, this means Supabase isn't configured.
        # We raise a 500 error instead of failing silently or falling back to local.
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Storage service is not configured properly."
        )

    if allowed_extensions is None:
        allowed_extensions = ALLOWED_EXTENSIONS

    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type '{ext}'. Allowed: {', '.join(allowed_extensions)}."
        )

    # Read bytes for upload
    contents = file.file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File '{file.filename}' exceeds maximum allowed size of 5 MB."
        )
    file.file.seek(0)

    # Generate canonical object path
    object_name = f"{uuid.uuid4().hex}{ext}"
    object_path = f"{folder}/{object_name}"

    content_type = mimetypes.guess_type(file.filename)[0] or "application/octet-stream"

    try:
        response = _supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).upload(
            path=object_path,
            file=contents,
            file_options={"content-type": content_type}
        )
        return object_path
    except Exception as e:
        # We do not expose the exact Supabase exception to the client
        print(f"Supabase Storage Upload Error: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to upload document to storage service."
        )

def delete_document(object_path: str):
    """
    Deletes a document from Supabase Storage. Useful for cleanup on failure.
    """
    if not _supabase or not object_path:
        return
    try:
        _supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).remove([object_path])
    except Exception as e:
        print(f"Supabase Storage Delete Error (Cleanup): {e}")

def get_signed_url(object_path: str, expires_in: int = 900) -> Optional[str]:
    """
    Generates a short-lived signed URL for a private document.
    Default expiration is 15 minutes (900 seconds).
    """
    if not object_path:
        return None
        
    # If the path is already an absolute URL (e.g. legacy http/data uri), just return it
    if object_path.startswith("http://") or object_path.startswith("https://") or object_path.startswith("data:"):
        return object_path

    # If it's a legacy local path (e.g. 'uploads/...'), do not sign it with Supabase.
    if object_path.startswith("uploads/"):
        return object_path

    if not _supabase:
        return object_path

    try:
        # Supabase Python client's create_signed_url returns a dictionary or string depending on version.
        # Handle dict or string response.
        response = _supabase.storage.from_(settings.SUPABASE_STORAGE_BUCKET).create_signed_url(object_path, expires_in)
        if isinstance(response, dict) and "signedURL" in response:
            return response["signedURL"]
        elif isinstance(response, str):
            return response
        elif hasattr(response, 'get'):
            return response.get('signedURL', response.get('signedUrl', object_path))
        else:
            # Fallback
            return response
    except Exception as e:
        print(f"Supabase Storage Signed URL Error: {e}")
        return None
