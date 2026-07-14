from fastapi import FastAPI, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from jose import jwt, JWTError
import models, schemas, auth, database
from database import engine, get_db
import os

# Initialize database tables
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Setup templates directory
templates = Jinja2Templates(directory="templates")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

# Dependency to get current user via JWT token
def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    try:
        payload = jwt.decode(token, auth.SECRET_KEY, algorithms=[auth.ALGORITHM])
        email: str = payload.get("sub")
    except JWTError:
        raise HTTPException(status_code=401, detail="Auth error")
        
    user = db.query(models.User).filter(models.User.email == email).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# Frontend UI Routes (Fixed Python 3.14 Keyword Arguments Layout)
@app.get("/", response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse(request=request, name="login.html")

@app.get("/register", response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse(request=request, name="register.html")

@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    # Reads the file directly, bypassing Jinja2's strict parser template checks
    template_path = os.path.join("templates", "dashboard.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()
    return HTMLResponse(content=html_content)

# Authentication Endpoints
@app.post("/auth/register", status_code=201)
def register(user_data: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.User).filter(models.User.email == user_data.email).first():
        raise HTTPException(status_code=400, detail="Email exists")
        
    role = "ADMIN" if db.query(models.User).count() == 0 else "USER"
    new_user = models.User(email=user_data.email, hashed_password=auth.get_password_hash(user_data.password), role=role)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    db.add(models.Wallet(balance=0.0, user_id=new_user.id))
    db.commit()
    return {"message": "Success", "role": role}

@app.post("/auth/login", response_model=schemas.Token)
def login(credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == credentials.email).first()
    if not user or not auth.verify_password(credentials.password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Wrong credentials")
    return {"access_token": auth.create_access_token({"sub": user.email}), "token_type": "bearer", "role": user.role}

# Wallet Operations Endpoints
@app.get("/wallet/balance", response_model=schemas.WalletResponse)
def get_balance(current_user: models.User = Depends(get_current_user)):
    return current_user.wallet

@app.post("/wallet/add", response_model=schemas.WalletResponse)
def add_money(data: schemas.TransactionCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    current_user.wallet.balance += data.amount
    db.add(models.Transaction(type="CREDIT", amount=data.amount, description=data.description or "Deposit", user_id=current_user.id))
    db.commit()
    return current_user.wallet

@app.post("/wallet/withdraw", response_model=schemas.WalletResponse)
def withdraw_money(data: schemas.TransactionCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.wallet.balance < data.amount:
        raise HTTPException(status_code=400, detail="No funds")
    current_user.wallet.balance -= data.amount
    db.add(models.Transaction(type="DEBIT", amount=data.amount, description=data.description or "Withdrawal", user_id=current_user.id))
    db.commit()
    return current_user.wallet

@app.post("/wallet/transfer")
def transfer_money(transfer: schemas.TransferRequest, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    if current_user.wallet.balance < transfer.amount:
        raise HTTPException(status_code=400, detail="No funds")
        
    rcpt = db.query(models.User).filter(models.User.email == transfer.recipient_email).first()
    if not rcpt:
        raise HTTPException(status_code=404, detail="Not found")
        
    current_user.wallet.balance -= transfer.amount
    rcpt.wallet.balance += transfer.amount
    
    db.add_all([
        models.Transaction(type="DEBIT", amount=transfer.amount, description="To " + transfer.recipient_email, user_id=current_user.id),
        models.Transaction(type="CREDIT", amount=transfer.amount, description="From " + current_user.email, user_id=rcpt.id)
    ])
    db.commit()
    return {"message": "Transferred"}

@app.get("/transactions", response_model=list[schemas.TransactionResponse])
def get_tx(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Transaction).filter(models.Transaction.user_id == current_user.id).all()

# --- BENEFICIARY ENDPOINTS ---
@app.post("/beneficiaries", response_model=schemas.BeneficiaryResponse)
def add_beneficiary(data: schemas.BeneficiaryCreate, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    target_user = db.query(models.User).filter(models.User.email == data.beneficiary_email).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Beneficiary user account not found")
        
    if data.beneficiary_email == current_user.email:
        raise HTTPException(status_code=400, detail="You cannot add yourself as a beneficiary")
        
    exists = db.query(models.Beneficiary).filter(
        models.Beneficiary.user_id == current_user.id,
        models.Beneficiary.beneficiary_email == data.beneficiary_email
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="Beneficiary already saved")
        
    new_beneficiary = models.Beneficiary(
        user_id=current_user.id,
        name=data.name,
        beneficiary_email=data.beneficiary_email
    )
    db.add(new_beneficiary)
    db.commit()
    db.refresh(new_beneficiary)
    return new_beneficiary

@app.get("/beneficiaries", response_model=list[schemas.BeneficiaryResponse])
def get_beneficiaries(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Beneficiary).filter(models.Beneficiary.user_id == current_user.id).all()

@app.delete("/beneficiaries/{beneficiary_id}")
def delete_beneficiary(beneficiary_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    beneficiary = db.query(models.Beneficiary).filter(
        models.Beneficiary.id == beneficiary_id,
        models.Beneficiary.user_id == current_user.id
    ).first()
    if not beneficiary:
        raise HTTPException(status_code=404, detail="Beneficiary not found")
        
    db.delete(beneficiary)
    db.commit()
    return {"message": "Beneficiary removed successfully"}

# Fixed entry-point execution path
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)