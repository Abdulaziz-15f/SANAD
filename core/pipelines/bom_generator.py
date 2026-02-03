import io
from typing import List, Dict, Optional

import xlsxwriter

def generate_bom_file(components: List[Dict], output_path: Optional[str] = None) -> Optional[bytes]:
    """
    Generate a BOM (Bill of Materials) Excel file.

    Args:
        components (List[Dict]): List of components with details (e.g., name, quantity, specs).
        output_path (str | None): Path to save the generated BOM file. If None, returns bytes.
    """
    buffer = None

    # Create a new Excel workbook and add a worksheet
    if output_path:
        workbook = xlsxwriter.Workbook(output_path)
    else:
        buffer = io.BytesIO()
        workbook = xlsxwriter.Workbook(buffer, {"in_memory": True})
    worksheet = workbook.add_worksheet("BOM")

    # Define header format
    header_format = workbook.add_format({
        'bold': True,
        'font_color': 'white',
        'bg_color': '#4CAF50',
        'border': 1
    })

    # Define cell format
    cell_format = workbook.add_format({'border': 1})

    # Write the header row
    headers = ["Component", "Description", "Quantity", "Unit", "Notes"]
    for col, header in enumerate(headers):
        worksheet.write(0, col, header, header_format)

    # Write component data
    for row, component in enumerate(components, start=1):
        worksheet.write(row, 0, component.get("name", ""), cell_format)
        worksheet.write(row, 1, component.get("description", ""), cell_format)
        worksheet.write(row, 2, component.get("quantity", ""), cell_format)
        worksheet.write(row, 3, component.get("unit", ""), cell_format)
        worksheet.write(row, 4, component.get("notes", ""), cell_format)

    # Adjust column widths
    worksheet.set_column(0, 0, 20)  # Component
    worksheet.set_column(1, 1, 40)  # Description
    worksheet.set_column(2, 2, 10)  # Quantity
    worksheet.set_column(3, 3, 10)  # Unit
    worksheet.set_column(4, 4, 30)  # Notes

    # Close the workbook
    workbook.close()

    if buffer:
        buffer.seek(0)
        return buffer.getvalue()
    return None
