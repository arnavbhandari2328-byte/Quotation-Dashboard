import os
from datetime import datetime
from fpdf import FPDF

def create_quotation_pdf(enquiry_data: dict, rate: str, payment_terms: str, pickup_location: str, gst: str):
    pdf = FPDF()
    pdf.add_page()
    
    # 1. Header 
    pdf.set_font("Helvetica", 'B', 12)
    pdf.cell(0, 5, "QUOTIFY", ln=True, align='C')
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(0, 5, "5-2-264, Opp.Govt.School,", ln=True, align='C')
    pdf.cell(0, 5, "Hyderbasti, Secunderabad -500003", ln=True, align='C')
    pdf.cell(0, 5, "No. 66385150 Fax No. 27548271 Email: contact@quotify.com", ln=True, align='C')
    pdf.cell(0, 5, "GST6: 36AADCN3182A1ZU", ln=True, align='C')
    
    # The Exclamation Border
    pdf.ln(2)
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(0, 5, "!"*110, ln=True, align='C')
    pdf.ln(5)

    # 2. Quotation Number & Date Line
    # Auto-generates a quote number using the database ID
    qt_no = str(enquiry_data.get('id', '1000'))[:4]
    current_date = datetime.now().strftime("%d-%m-%Y")
    
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(60, 5, f"QUT/{qt_no}", 0, 0, 'L')
    pdf.set_font("Helvetica", 'B', 10)
    pdf.cell(70, 5, "QUOTATION", 0, 0, 'C')
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(60, 5, current_date, 0, 1, 'R')
    pdf.ln(5)

    # 3. Customer Info
    customer = enquiry_data.get('customer_name', 'Customer')
    pdf.set_font("Helvetica", '', 10)
    pdf.cell(0, 5, f"M/s. {customer}", ln=True)
    pdf.cell(0, 5, f"       Kind Attn: Purchase Manager", ln=True)
    pdf.ln(5)

    # 4. Opening Paragraph
    pdf.multi_cell(0, 5, "With reference to your esteemed enquiry No.: we have pleasure to quote you our lowest rates as under and request you to favor us with your valued order at an early date.")
    pdf.ln(5)

    # 5. Exact Table Header
    pdf.set_font("Helvetica", 'B', 10)
    col_widths = [15, 80, 20, 25, 20, 30]
    pdf.cell(col_widths[0], 8, "Sl. No.", border=1, align='C')
    pdf.cell(col_widths[1], 8, "Description of the Materials", border=1, align='C')
    pdf.cell(col_widths[2], 8, "Qty", border=1, align='C')
    pdf.cell(col_widths[3], 8, "Rates", border=1, align='C')
    pdf.cell(col_widths[4], 8, "Units", border=1, align='C')
    pdf.cell(col_widths[5], 8, "HSN Code", border=1, align='C', ln=True)

    # 6. Table Data
    pdf.set_font("Helvetica", '', 10)
    # Merges product, grade, and size into one clean description
    product_desc = f"{enquiry_data.get('product_type', '')} {enquiry_data.get('material_grade', '')} {enquiry_data.get('size', '')}".strip()
    qty = str(enquiry_data.get('quantity', ''))
    unit = str(enquiry_data.get('unit', 'Nos'))
    hsn_code = "7304" # Default HSN
    
    pdf.cell(col_widths[0], 8, "1", border=1, align='C')
    pdf.cell(col_widths[1], 8, product_desc.title(), border=1, align='L')
    pdf.cell(col_widths[2], 8, qty, border=1, align='C')
    pdf.cell(col_widths[3], 8, rate, border=1, align='C')
    pdf.cell(col_widths[4], 8, unit, border=1, align='C')
    pdf.cell(col_widths[5], 8, hsn_code, border=1, align='C', ln=True)
    pdf.ln(5)

    # 7. Closing Text
    pdf.multi_cell(0, 5, "We hope that above offer is as per your requirement. If you need further clarification,\nPlease feel free to contact us. We shall be glad to respond you promptly. Awaiting your valuable purchase order.\nThanking you & assuring you of our best attention and services .")
    pdf.ln(5)

    # 8. Terms & Conditions (Strict Layout)
    pdf.cell(20, 5, "TERMS: ", 0, 0)
    pdf.cell(0, 5, f"1. Payment          :   {payment_terms}", 0, 1)
    
    pdf.cell(20, 5, "", 0, 0)
    pdf.cell(0, 5, f"2. F.O.R            :   {pickup_location}", 0, 1)
    
    pdf.cell(20, 5, "", 0, 0)
    pdf.cell(0, 5, f"3. G.S.T            :   {gst}", 0, 1)
    
    pdf.cell(20, 5, "", 0, 0)
    pdf.cell(0, 5, "4. Validity         :   5 - Days", 0, 1)
    
    pdf.cell(20, 5, "", 0, 0)
    pdf.cell(0, 5, "5. Delivery         :   Ready Stock", 0, 1)
    
    pdf.cell(20, 5, "", 0, 0)
    pdf.cell(0, 5, "6. Transport        :   At Actual", 0, 1)
    
    # 9. Signoff aligned exactly with the final term
    pdf.cell(20, 5, "", 0, 0)
    pdf.cell(80, 5, "7. P & F            :   Extra", 0, 0)
    pdf.cell(0, 5, "Your's faithfully,", 0, 1, align='R')
    
    pdf.cell(0, 5, "For Quotify", 0, 1, align='R')
    pdf.ln(10)
    pdf.cell(0, 5, "Arnav Bhandari", 0, 1, align='R')

    # Save the file
    base_dir = os.path.dirname(os.path.dirname(__file__))
    pdf_dir = os.path.join(base_dir, 'pdfs')
    os.makedirs(pdf_dir, exist_ok=True) 
    
    safe_name = str(customer).replace(' ', '_').replace('/', '')
    filepath = os.path.join(pdf_dir, f"Quote_{safe_name}.pdf")
    
    pdf.output(filepath)
    print(f"📄 PDF generated successfully: {filepath}")
    return filepath