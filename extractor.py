import pdfplumber
import sqlite3
import re
import os
import glob
import pandas as pd

def setup_database(db_path="parts_catalog.db"):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS parts")
    cursor.execute("DROP TABLE IF EXISTS cross_references")
    
    cursor.execute("""
    CREATE TABLE parts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        part_number TEXT UNIQUE,
        manufacturer TEXT,
        description TEXT,
        raw_specifications TEXT
    )
    """)
    cursor.execute("""
    CREATE TABLE cross_references (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        part_id INTEGER,
        competitor_brand TEXT,
        competitor_part_number TEXT,
        FOREIGN KEY (part_id) REFERENCES parts (id)
    )
    """)
    conn.commit()
    return conn, cursor

def extract_competitor_mfr(line):
    known_mfrs = [
        "BENDIX", "MERITOR", "HALDEX", "EATON", "SPICER", "DANA", 
        "NAVISTAR", "VOLVO", "MACK", "FREIGHTLINER", "CATERPILLAR", "CAT",
        "CUMMINS", "DETROIT DIESEL", "ROCKWELL", "ABEX", "GUNITE", 
        "MIDLAND", "STEMCO", "AUTOMANN", "EUCLID", "PETERBILT", 
        "KENWORTH", "FORD", "GM", "CHEVROLET", "ISUZU", "HINO"
    ]
    
    upper_line = line.upper()
    found_mfrs = []
    
    for mfr in known_mfrs:
        if re.search(rf'\b{mfr}\b', upper_line):
            found_mfrs.append(mfr)
            
    if found_mfrs:
        return ", ".join(found_mfrs)
    return "UNKNOWN OEM"

def clean_description(line, matched_pns, manufacturer):
    """Strips part numbers and brand names out of the line to leave only the description."""
    desc = line
    for pn in matched_pns:
        desc = desc.replace(pn, "")
        
    if manufacturer != "UNKNOWN OEM":
        for mfr in manufacturer.split(", "):
            desc = re.sub(rf'\b{mfr}\b', "", desc, flags=re.IGNORECASE)
            
    desc = re.sub(r'[^a-zA-Z0-9\s\-\.,/]', '', desc)
    desc = re.sub(r'\s+', ' ', desc).strip()
    desc = desc.strip(" -.,/")
    
    if not desc or len(desc) < 3:
        return "Heavy Duty Replacement Part"
    return desc

def get_primary_supplier(file_path):
    base_name = os.path.basename(file_path)
    name = os.path.splitext(base_name)[0]
    name = re.sub(r'(?i)\b(catalog|specs|guide|pdf|xlsx|csv)\b', '', name).strip()
    return name if name else "Unknown Supplier"

def process_single_pdf(pdf_path, cursor, pn_pattern, stop_words):
    primary_supplier = get_primary_supplier(pdf_path)
    print(f"Processing PDF: {os.path.basename(pdf_path)}...")

    with pdfplumber.open(pdf_path) as pdf:
        for page_num, page in enumerate(pdf.pages, start=1):
            text = page.extract_text(layout=True)
            if not text:
                continue
            
            for line in text.split('\n'):
                process_line(line, primary_supplier, cursor, pn_pattern, stop_words)

def process_spreadsheet(file_path, cursor, pn_pattern, stop_words):
    primary_supplier = get_primary_supplier(file_path)
    print(f"Processing Spreadsheet: {os.path.basename(file_path)}...")
    
    try:
        if file_path.lower().endswith('.csv'):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)
    except Exception as e:
        print(f"Error reading {os.path.basename(file_path)}: {e}")
        return
        
    for index, row in df.iterrows():
        line = " ".join(row.dropna().astype(str))
        process_line(line, primary_supplier, cursor, pn_pattern, stop_words)

def process_line(line, primary_supplier, cursor, pn_pattern, stop_words):
    raw_matches = pn_pattern.findall(line)
    matches = [m for m in raw_matches if m.upper() not in stop_words and len(m) >= 4]
    
    if len(matches) >= 2:
        primary_pn = matches[0]
        comp_mfr_name = extract_competitor_mfr(line)
        desc_text = clean_description(line, matches, comp_mfr_name)
        
        cursor.execute("""
            INSERT OR IGNORE INTO parts (part_number, manufacturer, description, raw_specifications)
            VALUES (?, ?, ?, ?)
        """, (primary_pn, primary_supplier, desc_text, line.strip()))
        
        cursor.execute("SELECT id FROM parts WHERE part_number = ?", (primary_pn,))
        part_row = cursor.fetchone()
        
        if part_row:
            part_id = part_row[0]
            for cross in set(matches[1:]):
                if cross != primary_pn:
                    cursor.execute("""
                        INSERT INTO cross_references (part_id, competitor_brand, competitor_part_number)
                        VALUES (?, ?, ?)
                    """, (part_id, comp_mfr_name, cross))

def main():
    db_path = "parts_catalog.db"
    conn, cursor = setup_database(db_path)
    
    pn_pattern = re.compile(r'\b([A-Z0-9]+[-][A-Z0-9]+|[A-Z]{2,}[0-9]+[A-Z0-9]*|[0-9]{5,}[A-Z]*)\b')
    stop_words = {"PAGE", "NOTES", "SIZE", "TYPE", "WIDTH", "LENGTH", "CROSS", "CROSSES"}

    all_files = []
    for ext in ["*.pdf", "*.csv", "*.xlsx", "*.xls"]:
        all_files.extend(glob.glob(os.path.join("catalogs", ext)))
    
    if not all_files:
        print("No valid files found in the 'catalogs' folder. Please add files and try again.")
        return

    print("Extracting true descriptions and OEMs...")
    for file_path in all_files:
        if file_path.lower().endswith('.pdf'):
            process_single_pdf(file_path, cursor, pn_pattern, stop_words)
        else:
            process_spreadsheet(file_path, cursor, pn_pattern, stop_words)

    conn.commit()
    conn.close()
    print("Database built successfully. Refresh your search app.")

if __name__ == "__main__":
    main()