from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List

from .. import crud, models, schemas
from ..core.database import get_db
from ..core.security import decrypt_api_key # For potential display of non-sensitive parts if ever needed

router = APIRouter()

@router.post("/", response_model=schemas.APIKeyStoredInfo, status_code=status.HTTP_201_CREATED)
def create_new_api_key(api_key_data: schemas.APIKeyCreate, db: Session = Depends(get_db)):
    # In a real multi-user app, you'd associate this with the current authenticated user.
    # For now, keys are global.
    # Consider adding a check if a key for that platform already exists for a user.
    db_api_key = crud.create_api_key(db=db, api_key_data=api_key_data)
    return schemas.APIKeyStoredInfo(id=db_api_key.id, platform=db_api_key.platform)

@router.get("/", response_model=List[schemas.APIKeyStoredInfo])
def read_api_keys(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    # In a real multi-user app, filter by current_user.id
    api_keys = crud.get_all_api_keys(db, skip=skip, limit=limit)
    return [schemas.APIKeyStoredInfo(id=key.id, platform=key.platform) for key in api_keys]

@router.get("/{api_key_id}", response_model=schemas.APIKeyStoredInfo)
def read_api_key(api_key_id: int, db: Session = Depends(get_db)):
    db_api_key = crud.get_api_key(db, api_key_id=api_key_id)
    if db_api_key is None:
        raise HTTPException(status_code=404, detail="API Key not found")
    # Again, ensure only non-sensitive info is returned
    return schemas.APIKeyStoredInfo(id=db_api_key.id, platform=db_api_key.platform)

@router.delete("/{api_key_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_existing_api_key(api_key_id: int, db: Session = Depends(get_db)):
    # Ensure the user owns this key in a multi-user app
    success = crud.delete_api_key(db, api_key_id=api_key_id)
    if not success:
        raise HTTPException(status_code=404, detail="API Key not found")
    return None # FastAPI will return 204 No Content

# Note: Updating API keys is often handled by deleting the old one and creating a new one,
# rather than an actual UPDATE operation on sensitive encrypted fields.
