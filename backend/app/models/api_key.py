from sqlalchemy import Column, Integer, String, Enum as SAEnum, ForeignKey
from sqlalchemy.orm import relationship
from ..core.database import Base
import enum

class PlatformEnum(str, enum.Enum):
    BYBIT = "bybit"
    WOOX = "woox"
    HYPERLIQUID = "hyperliquid"
    PARADEX = "paradex"

class APIKey(Base):
    __tablename__ = "api_keys"

    id = Column(Integer, primary_key=True, index=True)
    # user_id = Column(Integer, ForeignKey("users.id")) # If you add user accounts
    platform = Column(SAEnum(PlatformEnum), nullable=False)
    api_key_encrypted = Column(String, nullable=False)
    api_secret_encrypted = Column(String, nullable=True) # Not all platforms use a secret
    wallet_address_encrypted = Column(String, nullable=True) # For platforms like Hyperliquid
    # other_auth_details_encrypted = Column(String, nullable=True) # For generic storage

    # If you add user accounts:
    # owner = relationship("User", back_populates="api_keys")

    # A unique constraint to prevent duplicate keys for the same platform (and user, if applicable)
    # __table_args__ = (UniqueConstraint('user_id', 'platform', name='_user_platform_uc'),)
