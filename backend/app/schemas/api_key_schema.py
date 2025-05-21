from pydantic import BaseModel
from typing import Optional
from ..models.api_key import PlatformEnum # Re-use PlatformEnum from models

class APIKeyBase(BaseModel):
    platform: PlatformEnum
    api_key: str # Plain text on input
    api_secret: Optional[str] = None
    wallet_address: Optional[str] = None
    # other_auth_details: Optional[str] = None

class APIKeyCreate(APIKeyBase):
    pass

class APIKeyResponse(APIKeyBase):
    id: int
    # We will not return secrets or wallet addresses in the response for security,
    # only the platform and a masked/placeholder key if needed.
    # For now, let's return the platform and ID.
    # The actual key/secret will be stored encrypted and used by the backend only.
    
    api_key: str # Masked or placeholder, e.g., "********"
    api_secret: Optional[str] = None # Will be None or masked
    wallet_address: Optional[str] = None # Will be None or masked

    class Config:
        orm_mode = True # Pydantic V1, use from_attributes = True for V2
        # from_attributes = True # For Pydantic V2

# Schema for displaying a list of keys (perhaps without sensitive parts)
class APIKeyStoredInfo(BaseModel):
    id: int
    platform: PlatformEnum
    # Potentially a hint like last 4 chars of API key if needed, but generally avoid exposing.
    # For now, just platform and ID is safest for listing.

    class Config:
        orm_mode = True
        # from_attributes = True # For Pydantic V2
