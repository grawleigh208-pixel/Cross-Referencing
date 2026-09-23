import streamlit as st
import sqlite3
import pandas as pd
from rapidfuzz import process, fuzz

st.set_page_config(page_title="Heavy-Duty Parts Cross-Reference", layout="wide")

def get_connection():
    return sqlite3.connect("parts_catalog.db", check_same_thread=False)

conn = get_connection()

st.title("Heavy-Duty Parts Cross-Reference Engine")
st.markdown("Search across all loaded supplier catalogs by part number, cross-reference, or description.")

query = st.text_input("Enter Part Number, Cross-Reference, or Description Keyword:", "").strip()

if query:
    clean_q = f"%{query}%"
    
    # Exact or partial SQL match mapping to your exact requested column headers
    sql = """
    SELECT 
        p.part_number AS [Part Number],
        p.manufacturer AS [Supplier / Mfg Name],
        p.description AS [Description],
        cr.competitor_part_number AS [Cross Reference Part Number],
        cr.competitor_brand AS [Cross Reference Supplier Name]
    FROM parts p
    LEFT JOIN cross_references cr ON p.id = cr.part_id
    WHERE p.part_number LIKE ? 
       OR cr.competitor_part_number LIKE ?
       OR p.description LIKE ?
    """
    
    results = pd.read_sql_query(sql, conn, params=(clean_q, clean_q, clean_q))
    
    if not results.empty:
        st.success(f"Found {len(results)} matching record(s)")
        st.dataframe(results, use_container_width=True, hide_index=True)
    else:
        st.warning("No direct match found. Running fuzzy search on part numbers...")
        
        all_parts = pd.read_sql_query("SELECT part_number FROM parts", conn)["part_number"].tolist()
        all_crosses = pd.read_sql_query("SELECT competitor_part_number FROM cross_references", conn)["competitor_part_number"].tolist()
        
        candidates = list(set(filter(None, all_parts + all_crosses)))
        
        fuzzy_matches = process.extract(query, candidates, scorer=fuzz.token_sort_ratio, limit=5)
        matched_terms = [match[0] for match in fuzzy_matches if match[1] >= 65]
        
        if matched_terms:
            placeholders = ",".join(["?"] * len(matched_terms))
            fuzzy_sql = f"""
            SELECT 
                p.part_number AS [Part Number],
                p.manufacturer AS [Supplier / Mfg Name],
                p.description AS [Description],
                cr.competitor_part_number AS [Cross Reference Part Number],
                cr.competitor_brand AS [Cross Reference Supplier Name]
            FROM parts p
            LEFT JOIN cross_references cr ON p.id = cr.part_id
            WHERE p.part_number IN ({placeholders}) OR cr.competitor_part_number IN ({placeholders})
            """
            fuzzy_results = pd.read_sql_query(fuzzy_sql, conn, params=matched_terms * 2)
            st.info("Closest part number matches based on partial input:")
            st.dataframe(fuzzy_results, use_container_width=True, hide_index=True)
        else:
            st.error("No close matches found. Verify your search term and try again.")