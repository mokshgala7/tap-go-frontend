import pytest
from unittest.mock import patch, MagicMock
from fastapi import UploadFile, HTTPException
from io import BytesIO
import os

from app.utils.storage_service import upload_document, get_signed_url, delete_document, MAX_FILE_SIZE

@pytest.fixture
def mock_supabase():
    with patch("app.utils.storage_service._supabase") as mock_client:
        mock_storage = MagicMock()
        mock_client.storage.from_.return_value = mock_storage
        yield mock_storage

def create_mock_upload_file(filename: str, size: int) -> UploadFile:
    content = b"a" * size
    file_obj = BytesIO(content)
    upload_file = UploadFile(filename=filename, file=file_obj)
    return upload_file

def test_successful_image_upload(mock_supabase):
    file = create_mock_upload_file("test_photo.jpg", 1024)
    result = upload_document(file, "profile")
    
    assert result.startswith("profile/")
    assert result.endswith(".jpg")
    mock_supabase.upload.assert_called_once()
    
    # Assert private bucket is used by checking that from_ is called with the bucket name
    import app.utils.storage_service as ss
    from_args = ss._supabase.storage.from_.call_args[0][0]
    assert from_args == ss.settings.SUPABASE_STORAGE_BUCKET

def test_successful_pdf_upload(mock_supabase):
    file = create_mock_upload_file("doc.pdf", 1024)
    result = upload_document(file, "id_documents", [".pdf"])
    
    assert result.startswith("id_documents/")
    assert result.endswith(".pdf")
    mock_supabase.upload.assert_called_once()

def test_invalid_file_type(mock_supabase):
    file = create_mock_upload_file("script.sh", 1024)
    with pytest.raises(HTTPException) as excinfo:
        upload_document(file, "profile")
    assert excinfo.value.status_code == 400
    assert "Unsupported file type" in excinfo.value.detail

def test_oversized_file(mock_supabase):
    file = create_mock_upload_file("huge.jpg", MAX_FILE_SIZE + 1024)
    with pytest.raises(HTTPException) as excinfo:
        upload_document(file, "profile")
    assert excinfo.value.status_code == 400
    assert "exceeds maximum allowed size" in excinfo.value.detail

def test_storage_upload_failure(mock_supabase):
    mock_supabase.upload.side_effect = Exception("Network error")
    file = create_mock_upload_file("test.jpg", 1024)
    with pytest.raises(HTTPException) as excinfo:
        upload_document(file, "profile")
    assert excinfo.value.status_code == 500
    assert "Failed to upload document" in excinfo.value.detail

def test_signed_url_generation(mock_supabase):
    mock_supabase.create_signed_url.return_value = {"signedURL": "https://signed.url"}
    url = get_signed_url("profile/123.jpg", expires_in=900)
    assert url == "https://signed.url"
    mock_supabase.create_signed_url.assert_called_with("profile/123.jpg", 900)

def test_signed_url_passthrough():
    # Absolute URL
    url = get_signed_url("https://example.com/test.jpg")
    assert url == "https://example.com/test.jpg"
    
    # Legacy uploads
    url = get_signed_url("uploads/profile/test.jpg")
    assert url == "uploads/profile/test.jpg"

def test_delete_document(mock_supabase):
    delete_document("profile/123.jpg")
    mock_supabase.remove.assert_called_once_with(["profile/123.jpg"])
