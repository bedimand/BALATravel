from uuid import uuid4

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Export, Trip


settings = get_settings()


def create_pdf_export(db: Session, trip: Trip) -> Export:
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    filename = f"trip-{trip.id}-{uuid4().hex[:8]}.pdf"
    filepath = settings.storage_dir / filename
    pdf = canvas.Canvas(str(filepath), pagesize=A4)
    pdf.setTitle(f"BALATravel - {trip.destination}")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(50, 800, f"BALATravel - {trip.destination}")
    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, 780, f"Periodo: {trip.start_date.isoformat()} a {trip.end_date.isoformat()}")
    pdf.drawString(50, 764, f"Estilo: {trip.style} | Orcamento: {trip.budget}")
    line_y = 730
    active = next((version for version in reversed(trip.itinerary_versions) if version.status == "active"), None)
    if active:
        pdf.drawString(50, line_y, "Roteiro")
        line_y -= 20
        for item in sorted(active.items, key=lambda row: (row.date, row.start_time)):
            pdf.drawString(
                60,
                line_y,
                f"{item.date.isoformat()} {item.start_time.strftime('%H:%M')} - {item.title} ({item.item_type})",
            )
            line_y -= 16
            if line_y < 60:
                pdf.showPage()
                pdf.setFont("Helvetica", 11)
                line_y = 800
    pdf.save()
    export = Export(trip_id=trip.id, format="pdf", file_url=f"storage/exports/{filename}")
    db.add(export)
    db.commit()
    db.refresh(export)
    return export

