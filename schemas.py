from pydantic import BaseModel, EmailStr
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    role: str

class WalletResponse(BaseModel):
    balance: float
    class Config: from_attributes = True

class TransactionCreate(BaseModel):
    amount: float
    description: Optional[str] = None

class TransferRequest(BaseModel):
    recipient_email: EmailStr
    amount: float
    description: Optional[str] = None

class TransactionResponse(BaseModel):
    id: int
    type: str
    amount: float
    description: Optional[str] = None
    timestamp: datetime
    class Config: from_attributes = True

class KycUpdate(BaseModel):
    status: str

class BeneficiaryCreate(BaseModel):
    name: str
    beneficiary_email: EmailStr

class BeneficiaryResponse(BaseModel):
    id: int
    name: str
    beneficiary_email: str

    class Config:
        from_attributes = True