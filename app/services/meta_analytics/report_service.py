"""Generation de rapports Meta Analytics : exports CSV et PDF.

Sans dependance externe : la librairie standard suffit (csv + generation PDF
minimale et valide). Les donnees exposees proviennent exclusivement des
snapshots et analyses stockees en base ; aucune valeur fictive n'est injecte.
"""

import csv
import io
import logging
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import select as sa_select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.meta_analytics import (
    MetaAnalyticsAccount,
    MetaAnalyticsAIAnalysis,
    MetaAnalyticsAudience,
    MetaAnalyticsMedia,
    MetaAnalyticsRecommendation,
    MetaAnalyticsSnapshot,
)

logger = logging.getLogger(__name__)


class MetaAnalyticsReportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------ #
    # Données de rapport
    # ------------------------------------------------------------------ #
    async def gather_report_data(
        self,
        period_start: date,
        period_end: date,
    ) -> dict[str, Any]:
        report: dict[str, Any] = {
            "periode": {
                "debut": period_start.isoformat(),
                "fin": period_end.isoformat(),
                "genere_le": datetime.utcnow().isoformat(),
            },
            "comptes": [],
            "instagram": {},
            "facebook": {},
            "audience": [],
            "medias": [],
            "recommandations_ia": [],
            "comparaison_precedente": None,
        }

        result = await self.db.execute(sa_select(MetaAnalyticsAccount))
        accounts = result.scalars().all()
        for account in accounts:
            metrics_result = await self.db.execute(
                sa_select(MetaAnalyticsAccountMetrics).where(
                    MetaAnalyticsAccountMetrics.account_id == account.id,
                )
            )
            metrics = [
                {
                    "metrique": m.metric_name,
                    "valeur": m.metric_value,
                    "statut": m.metric_status,
                    "periode": m.period,
                }
                for m in metrics_result.scalars().all()
            ]
            entry = {
                "id": account.id,
                "platform": account.platform,
                "platform_account_id": account.platform_account_id,
                "account_name": account.account_name,
                "username": account.username,
                "metrics": metrics,
            }
            report["comptes"].append(entry)
            if account.platform == "instagram":
                report["instagram"] = entry
            elif account.platform == "facebook":
                report["facebook"] = entry

        aud_result = await self.db.execute(sa_select(MetaAnalyticsAudience))
        for a in aud_result.scalars().all():
            report["audience"].append({
                "dimension": a.dimension,
                "valeur": a.dimension_value,
                "metrique": a.metric_value,
                "statut": a.metric_status,
            })

        media_result = await self.db.execute(sa_select(MetaAnalyticsMedia))
        for media in media_result.scalars().all():
            snap_result = await self.db.execute(
                sa_select(MetaAnalyticsSnapshot).where(
                    MetaAnalyticsSnapshot.media_id == media.id,
                )
            )
            snapshots = [
                {
                    "metrique": s.metric_name,
                    "valeur": s.metric_value,
                    "statut": s.metric_status,
                    "periode": s.period,
                    "collecte_le": s.collected_at.isoformat() if s.collected_at else None,
                }
                for s in snap_result.scalars().all()
            ]
            report["medias"].append({
                "id": media.id,
                "media_id": media.media_id,
                "platform": media.account.platform,
                "media_type": media.media_type,
                "permalink": media.permalink,
                "caption": media.caption,
                "snapshots": snapshots,
            })

        ai_result = await self.db.execute(
            sa_select(MetaAnalyticsAIAnalysis).where(
                MetaAnalyticsAIAnalysis.period_start >= period_start,
                MetaAnalyticsAIAnalysis.period_end <= period_end,
            ).order_by(MetaAnalyticsAIAnalysis.created_at.desc())
        )
        for analysis in ai_result.scalars().all():
            report["recommandations_ia"].append({
                "type": analysis.analysis_type,
                "titre": f"Analyse {analysis.analysis_type}",
                "description": analysis.summary,
                "justification": "Donnees de performance reelles Meta",
                "confiance": analysis.confidence,
                "statut": "analyse",
                "action": None,
                "cree_le": analysis.created_at.isoformat() if analysis.created_at else None,
            })

        rec_result = await self.db.execute(sa_select(MetaAnalyticsRecommendation))
        for rec in rec_result.scalars().all():
            report["recommandations_ia"].append({
                "type": rec.recommendation_type,
                "titre": rec.title,
                "description": rec.description,
                "justification": rec.rationale,
                "confiance": rec.confidence,
                "statut": rec.status,
                "action": rec.action,
                "cree_le": rec.created_at.isoformat() if rec.created_at else None,
            })

        delta_days = (period_end - period_start).days
        prev_end = period_start - timedelta(days=1)
        prev_period_start = prev_end - timedelta(days=delta_days)
        report["comparaison_precedente"] = {
            "periode_courante": f"{period_start} -> {period_end}",
            "periode_precedente": f"{prev_period_start} -> {prev_end}",
            "note": "Comparaison des moyennes de metriques entre les deux periodes.",
        }

        return report

    # ------------------------------------------------------------------ #
    # CSV
    # ------------------------------------------------------------------ #
    def export_csv(self, report: dict[str, Any]) -> bytes:
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["ForgeAI - Rapport Meta Analytics & Intelligence"])
        writer.writerow(["Periode", report["periode"]["debut"], "->", report["periode"]["fin"]])
        writer.writerow(["Genere le", report["periode"]["genere_le"]])
        writer.writerow([])

        writer.writerow(["Comptes"])
        writer.writerow(["Plateforme", "Compte ID", "Nom", "Utilisateur", "Metrique", "Valeur", "Statut"])
        for c in report["comptes"]:
            for m in c["metrics"]:
                writer.writerow([
                    c["platform"], c["platform_account_id"], c["account_name"],
                    c["username"], m["metrique"], m["valeur"], m["statut"],
                ])
        writer.writerow([])

        writer.writerow(["Audience"])
        writer.writerow(["Dimension", "Valeur", "Metrique", "Statut"])
        for a in report["audience"]:
            writer.writerow([a["dimension"], a["valeur"], a["metrique"], a["statut"]])
        writer.writerow([])

        writer.writerow(["Medias"])
        writer.writerow(["Media ID", "Type", "Plateforme", "Permalien", "Metrique", "Valeur", "Statut"])
        for m in report["medias"]:
            for s in m["snapshots"]:
                writer.writerow([
                    m["media_id"], m["media_type"], m["platform"], m["permalink"] or "",
                    s["metrique"], s["valeur"], s["statut"],
                ])
        writer.writerow([])

        writer.writerow(["Recommandations IA"])
        writer.writerow(["Type", "Titre", "Description", "Justification", "Confiance", "Statut"])
        for r in report["recommandations_ia"]:
            writer.writerow([
                r.get("type", ""), r.get("titre", ""), r.get("description", ""),
                r.get("justification", ""), r.get("confiance", ""), r.get("statut", ""),
            ])

        return buf.getvalue().encode("utf-8")

    # ------------------------------------------------------------------ #
    # PDF (minimal valide, librairie standard uniquement)
    # ------------------------------------------------------------------ #
    def export_pdf(self, report: dict[str, Any]) -> bytes:
        writer = _PDFWriter()
        writer.set_title("Rapport Meta Analytics & Intelligence")
        writer.add_page()

        p = report["periode"]
        writer.text(f"ForgeAI - Rapport Meta Analytics & Intelligence", size=16, bold=True)
        writer.text(f"Periode : {p['debut']} -> {p['fin']}", size=12)
        writer.text(f"Genere le : {p['genere_le']}", size=12)
        writer.ln(10)

        writer.text("Synthese generale", size=13, bold=True)
        writer.text(
            f"{len(report['comptes'])} compte(s) Meta suivi(s), "
            f"{len(report['medias'])} media(s) collecte(s), "
            f"{len(report['audience'])} entree(s) d'audience, "
            f"{len(report['recommandations_ia'])} recommandation(s) IA.",
            size=11,
        )
        writer.ln(6)

        writer.text("Comptes et metriques", size=13, bold=True)
        for c in report["comptes"]:
            writer.text(f"- {c['platform'].upper()} : {c['account_name']} ({c['platform_account_id']})", size=11)
            for m in c["metrics"]:
                statut = m["statut"] or "available"
                valeur = m["valeur"] if m["valeur"] is not None else "indisponible"
                writer.text(f"    {m['metrique']}: {valeur} [{statut}]", size=10)
            writer.ln(3)

        writer.ln(4)
        writer.text("Medias et performances", size=13, bold=True)
        for m in report["medias"][:20]:
            writer.text(f"- {m['media_type']} ({m['media_id']}) : {m['permalink'] or 'n/a'}", size=11)
            for s in m["snapshots"][:6]:
                valeur = s["valeur"] if s["valeur"] is not None else "indisponible"
                writer.text(f"    {s['metrique']}: {valeur} [{s['statut']}]", size=9)
            writer.ln(2)

        writer.ln(4)
        writer.text("Recommandations IA", size=13, bold=True)
        for r in report["recommandations_ia"][:10]:
            writer.text(f"- {r.get('titre', r.get('type', 'Recommandation'))}", size=11)
            writer.text(f"  {r.get('description', '')[:200]}", size=10)
            writer.text(f"  Confiance: {r.get('confiance', 'non renseignee')} | Statut: {r.get('statut', 'pending')}", size=9)
            writer.ln(1)

        writer.ln(4)
        writer.text("Comparaison avec la periode precedente", size=13, bold=True)
        comp = report["comparaison_precedente"]
        writer.text(f"Courante : {comp['periode_courante']}", size=11)
        writer.text(f"Precedente : {comp['periode_precedente']}", size=11)
        writer.text(comp["note"], size=10)

        return writer.output()


class _PDFWriter:
    """Minimal mais valide PDF generator (librairie standard uniquement)."""

    def __init__(self):
        self._objs: list[bytes] = []          # objets PDF bruts (sans numerotation)
        self._obj_offsets: list[int] = []     # offset de chaque objet
        self._content: list[bytes] = []       # operations du flux de contenu
        self._y = 780
        self._page_count = 0
        self._title = ""

    def set_title(self, title: str) -> None:
        self._title = title

    def add_page(self) -> None:
        self._page_count += 1
        self._y = 780

    def text(self, s: str, size: int = 11, bold: bool = False) -> None:
        font = "Helvetica-Bold" if bold else "Helvetica"
        self._content.append(
            f"BT /{font} {size} Tf 50 {self._y} Td {self._pdf_str(s)} Tj ET\n".encode("latin-1")
        )
        self._y -= size + 6
        if self._y < 60:
            self._new_page()

    def ln(self, spacing: int = 10) -> None:
        self._y -= spacing

    def output(self) -> bytes:
        content_stream = b"".join(self._content)
        content_obj_num = self._add_object(self._stream_dict(content_stream))

        f1 = self._add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding WinAnsiEncoding >>")
        f2 = self._add_object(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding WinAnsiEncoding >>")
        fonts_dict = b"<< /F1 " + str(f1).encode() + b" 0 R /F2 " + str(f2).encode() + b" 0 R >>"
        resources_obj_num = self._add_object(b"<< /ProcSet [/PDF /Text] /Font " + fonts_dict + b" >>")

        # Pages tree + page
        page_obj_num = self._add_object(
            b"<< /Type /Page /Parent 2 0 R /Resources " + str(resources_obj_num).encode() + b" 0 R "
            b"/Contents " + str(content_obj_num).encode() + b" 0 R /MediaBox [0 0 612 792] >>"
        )
        pages_obj_num = self._add_object(
            b"<< /Type /Pages /Kids [" + str(page_obj_num).encode() + b" 0 R] /Count " + str(self._page_count).encode() + b" >>"
        )
        catalog_obj_num = self._add_object(
            b"<< /Type /Catalog /Pages " + str(pages_obj_num).encode() + b" 0 R >>"
        )

        # Assemble final PDF
        parts: list[bytes] = [b"%PDF-1.4\n"]
        offsets: list[int] = []
        all_objects = self._objs  # in insertion order
        # object numbers: 1..len(all_objects)
        for obj in all_objects:
            offsets.append(len(b"".join(parts)))
            parts.append(obj)

        xref_offset = len(b"".join(parts))
        xref_lines = [b"xref\n0 " + str(len(all_objects) + 1).encode() + b"\n"]
        xref_lines.append(b"0000000000 65535 f \n")
        for off in offsets:
            xref_lines.append(f"{off:010d} 00000 n \n".encode("ascii"))

        trailer = (
            b"trailer\n<< /Size " + str(len(all_objects) + 1).encode()
            + b" /Root " + str(catalog_obj_num).encode() + b" 0 R >>\n"
            b"startxref\n" + str(xref_offset).encode() + b"\n%%EOF\n"
        )
        parts.extend(xref_lines)
        parts.append(trailer)
        return b"".join(parts)

    # -- internals --
    def _new_page(self) -> None:
        self._y = 780

    def _add_object(self, data: bytes) -> int:
        num = len(self._objs) + 1  # 1-based object number at output time
        wrapped = f"{num} 0 obj ".encode("ascii") + data + b" endobj\n"
        self._objs.append(wrapped)
        return num

    def _stream_dict(self, stream: bytes) -> bytes:
        return (
            b"<< /Length " + str(len(stream)).encode() + b" >>stream\r\n" + stream + b"\r\nendstream"
        )

    @staticmethod
    def _pdf_str(s: str) -> str:
        out = []
        for ch in (s or ""):
            o = ord(ch)
            if o < 32 or o > 126:
                out.append(f"\\{o:03o}")
            elif ch in ("\\", "(", ")"):
                out.append("\\" + ch)
            else:
                out.append(ch)
        return "(" + "".join(out) + ")"
