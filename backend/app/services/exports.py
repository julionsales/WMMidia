"""Exportação tabular (CSV com BOM para Excel e XLSX), como no script original."""

from __future__ import annotations

import csv
import io
from datetime import datetime

from openpyxl import Workbook
from openpyxl.utils import get_column_letter

from app.core.timeutil import fmt_local

VEHICLE_COLUMNS = [
    ("company_name", "Empresa"), ("brand_display", "Marca"), ("model", "Modelo"), ("version", "Versão"),
    ("year_fabrication", "Ano fabricação"), ("year_model", "Ano modelo"), ("km", "Km"), ("price", "Preço"),
    ("price_on_request", "Sob consulta"), ("status", "Situação"), ("first_seen_at", "Primeira observação"),
    ("last_seen_at", "Última observação"), ("missing_since", "Não encontrado desde"), ("observed_days", "Dias observado"),
    ("price_change_count", "Alterações de preço"), ("source_id", "ID na origem"), ("vehicle_key", "Chave interna"),
    ("url", "Link"),
]
POST_COLUMNS = [
    ("taken_at", "Data"), ("format", "Formato"), ("caption", "Legenda"), ("likes", "Curtidas"),
    ("comments", "Comentários"), ("interaction_value", "Interação pública estimada (%)"),
    ("followers_used", "Seguidores usados"), ("followers_basis", "Base dos seguidores"),
    ("observed_at", "Métricas observadas em"), ("url", "Link"),
]
STATUS_LABELS = {"ativo": "Ativo", "nao_encontrado": "Não encontrado na última coleta"}


def _cell(value):
    if isinstance(value, datetime):
        return fmt_local(value)
    if isinstance(value, bool):
        return "sim" if value else "não"
    if value is None:
        return ""
    return STATUS_LABELS.get(value, value) if isinstance(value, str) else value


def to_csv(rows: list[dict], columns: list[tuple[str, str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";")
    writer.writerow([label for _, label in columns])
    for row in rows:
        writer.writerow([_cell(row.get(key)) for key, _ in columns])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def to_xlsx(sheets: dict[str, tuple[list[dict], list[tuple[str, str]]]]) -> bytes:
    wb = Workbook()
    wb.remove(wb.active)
    for name, (rows, columns) in sheets.items():
        ws = wb.create_sheet(title=name[:31])
        ws.append([label for _, label in columns])
        for row in rows:
            ws.append([_cell(row.get(key)) for key, _ in columns])
        for i, (_, label) in enumerate(columns, start=1):
            ws.column_dimensions[get_column_letter(i)].width = max(12, min(48, len(label) + 4))
        ws.freeze_panes = "A2"
    buffer = io.BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


def flatten_post(post: dict) -> dict:
    interaction = post.get("interaction") or {}
    metrics = post.get("latest_metrics") or {}
    return {
        **post,
        "interaction_value": interaction.get("value"),
        "followers_used": interaction.get("followers"),
        "followers_basis": {"snapshot_proximo": "Snapshot próximo à publicação",
                            "seguidores_da_coleta": "Seguidores da coleta"}.get(interaction.get("basis"), ""),
        "observed_at": metrics.get("observed_at"),
    }
