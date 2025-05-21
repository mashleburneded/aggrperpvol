from sqlalchemy.orm import Session
from .. import models, schemas
from ..core.security import encrypt_api_key, decrypt_api_key # Ensure this path is correct

def get_api_key(db: Session, api_key_id: int):
    return db.query(models.APIKey).filter(models.APIKey.id == api_key_id).first()

def get_api_keys_by_platform(db: Session, platform: schemas.PlatformEnum, skip: int = 0, limit: int = 100):
    # This would typically be filtered by user_id as well in a multi-user system
    return db.query(models.APIKey).filter(models.APIKey.platform == platform).offset(skip).limit(limit).all()

def get_all_api_keys(db: Session, skip: int = 0, limit: int = 100):
    # This would typically be filtered by user_id as well
    return db.query(models.APIKey).offset(skip).limit(limit).all()

def create_api_key(db: Session, api_key_data: schemas.APIKeyCreate):
    encrypted_key = encrypt_api_key(api_key_data.api_key)
    encrypted_secret = encrypt_api_key(api_key_data.api_secret) if api_key_data.api_secret else None
    encrypted_wallet_address = encrypt_api_key(api_key_data.wallet_address) if api_key_data.wallet_address else None
    
    db_api_key = models.APIKey(
        platform=api_key_data.platform,
        api_key_encrypted=encrypted_key,
        api_secret_encrypted=encrypted_secret,
        wallet_address_encrypted=encrypted_wallet_address
        # user_id=current_user.id # If using user accounts
    )
    db.add(db_api_key)
    db.commit()
    db.refresh(db_api_key)
    return db_api_key

def delete_api_key(db: Session, api_key_id: int):
    db_api_key = db.query(models.APIKey).filter(models.APIKey.id == api_key_id).first()
    if db_api_key:
        db.delete(db_api_key)
        db.commit()
        return True
    return False

# Helper to get decrypted key for backend use (use with extreme caution)
def get_decrypted_api_key_details(db: Session, api_key_id: int) -> schemas.APIKeyBase | None:
    db_key = get_api_key(db, api_key_id)
    if not db_key:
        return None
    
    return schemas.APIKeyBase(
        platform=db_key.platform,
        api_key=decrypt_api_key(db_key.api_key_encrypted),
        api_secret=decrypt_api_key(db_key.api_secret_encrypted) if db_key.api_secret_encrypted else None,
        wallet_address=decrypt_api_key(db_key.wallet_address_encrypted) if db_key.wallet_address_encrypted else None
    )
