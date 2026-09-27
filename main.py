from fastapi import FastAPI, Depends
from pydantic import BaseModel, Field
from typing import List
import sqlite3

app = FastAPI(
    title="Data Processing & Subsidy Matcher API",
    description="Collects farmer data, processes eligibility, and provides subsidy application links."
)

def get_db():
    conn = sqlite3.connect("app_data.db")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    conn = sqlite3.connect("app_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            farmer_name TEXT NOT NULL,
            state TEXT NOT NULL,
            land_acres REAL NOT NULL,
            crop_type TEXT NOT NULL,
            annual_income REAL NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS subsidies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            max_land_limit REAL,
            max_income_limit REAL,
            target_crop TEXT,
            description TEXT,
            apply_url TEXT NOT NULL
        )
    """)
    cursor.execute("SELECT COUNT(*) FROM subsidies")
    if cursor.fetchone()[0] == 0:
        sample_subsidies = [
            ("PM-KISAN Income Support", "Direct Benefit", 5.0, 200000.0, "All", "Financial assistance of ₹6,000 per year for small and marginal landholders.", "https://pmkisan.gov.in/"),
            ("PM Krishi Sinchayee Yojana (Drip Irrigation)", "Irrigation", 10.0, 500000.0, "All", "Up to 55% subsidy on micro-irrigation equipment installations.", "https://pmksy.gov.in/"),
            ("Sub-Mission on Agricultural Mechanization (SMAM)", "Machinery", 15.0, 800000.0, "All", "Financial assistance for purchasing tractors, tillers, and harvesters.", "https://agrimachinery.nic.in/"),
            ("Horticulture Mission for Commercial Crops", "Crop Incentive", 20.0, 1000000.0, "Vegetables", "Special seed and fertilizer subsidy for high-yield horticulture crops.", "https://midh.gov.in/")
        ]
        cursor.executemany("""
            INSERT INTO subsidies (title, category, max_land_limit, max_income_limit, target_crop, description, apply_url)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, sample_subsidies)
        conn.commit()
    conn.close()

init_db()

class UserInput(BaseModel):
    farmer_name: str = Field(..., example="Godwin Antony")
    state: str = Field(..., example="Kerala")
    land_acres: float = Field(..., example=2.5)
    crop_type: str = Field(..., example="Vegetables")
    annual_income: float = Field(..., example=150000.0)

class SubsidyMatch(BaseModel):
    title: str
    category: str
    description: str
    apply_url: str

class ProcessingResult(BaseModel):
    submission_id: int
    farmer_name: str
    status: str
    matched_subsidies_count: int
    eligible_subsidies: List[SubsidyMatch]

def process_and_match(user: UserInput, db: sqlite3.Connection) -> List[SubsidyMatch]:
    cursor = db.cursor()
    cursor.execute("SELECT * FROM subsidies")
    rows = cursor.fetchall()
    
    matched = []
    for row in rows:
        land_ok = user.land_acres <= row["max_land_limit"]
        income_ok = user.annual_income <= row["max_income_limit"]
        crop_ok = row["target_crop"] == "All" or row["target_crop"].lower() == user.crop_type.lower()
        
        if land_ok and income_ok and crop_ok:
            matched.append(SubsidyMatch(
                title=row["title"],
                category=row["category"],
                description=row["description"],
                apply_url=row["apply_url"]
            ))
    return matched

@app.post("/api/v1/collect-and-process", response_model=ProcessingResult)
def collect_and_process_data(data: UserInput, db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("""
        INSERT INTO user_submissions (farmer_name, state, land_acres, crop_type, annual_income)
        VALUES (?, ?, ?, ?, ?)
    """, (data.farmer_name, data.state, data.land_acres, data.crop_type, data.annual_income))
    db.commit()
    submission_id = cursor.lastrowid
    
    eligible_schemes = process_and_match(data, db)
    return ProcessingResult(
        submission_id=submission_id,
        farmer_name=data.farmer_name,
        status="Successfully Processed",
        matched_subsidies_count=len(eligible_schemes),
        eligible_subsidies=eligible_schemes
    )

@app.get("/api/v1/subsidies", response_model=List[SubsidyMatch])
def get_all_subsidies(db: sqlite3.Connection = Depends(get_db)):
    cursor = db.cursor()
    cursor.execute("SELECT title, category, description, apply_url FROM subsidies")
    rows = cursor.fetchall()
    return [SubsidyMatch(**dict(r)) for r in rows]