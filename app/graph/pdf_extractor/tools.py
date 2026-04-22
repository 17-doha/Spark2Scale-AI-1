import io
import re

try:
    from PyPDF2 import PdfReader
except ImportError:
    PdfReader = None

def force_numeric_types(data: any) -> any:
    """
    Recursively ensures fields that should be numbers are actually numbers.
    Prevents '>' errors between str and int.
    """
    numeric_fields = {
        "amount_raised_to_date", "target_amount", "ownership_percentage", 
        "years_direct_experience", "interviews_conducted", "user_count", 
        "active_users_monthly", "early_revenue", "growth_rate", 
        "average_price_per_customer", "gross_margin", "monthly_burn", "runway_months"
    }
    
    if isinstance(data, dict):
        for key, value in data.items():
            if key in numeric_fields:
                if isinstance(value, str):
                    # Remove everything except digits and decimal points
                    clean_val = re.sub(r'[^0-9.]', '', value)
                    try:
                        data[key] = float(clean_val) if '.' in clean_val else int(clean_val)
                    except ValueError:
                        data[key] = 0
                elif value is None:
                    data[key] = 0
            else:
                force_numeric_types(value)
    elif isinstance(data, list):
        for item in data:
            force_numeric_types(item)
    return data

def extract_text_from_pdf(file_bytes: bytes) -> str:
    if PdfReader is None:
        raise ImportError("PyPDF2 is not installed. Run: pip install PyPDF2")
    reader = PdfReader(io.BytesIO(file_bytes))
    pages_text = [p.extract_text() for p in reader.pages if p.extract_text()]
    return "\n\n".join(pages_text)
