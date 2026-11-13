"""Geração do DOCX do briefing (evolução do make_briefing_docx do script original).

Gerado a partir do briefing salvo (dados congelados): o mesmo briefing produz sempre
o mesmo conteúdo.
"""

from __future__ import annotations

import io

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt, RGBColor

from app.core.timeutil import fmt_local, parse_iso

FORMAT_LABELS = {"imagem": "Imagem", "video": "Vídeo", "reels": "Reels", "carrossel": "Carrossel", "desconhecido": "Não identificado"}


def brl(value) -> str:
    if value is None:
        return "Sob consulta / não informado"
    return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def num(value, suffix: str = "") -> str:
    if value is None:
        return "indisponível"
    if isinstance(value, float):
        return f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") + suffix
    return f"{value:,}".replace(",", ".") + suffix


def date(value: str | None, with_time: bool = False) -> str:
    return fmt_local(parse_iso(value), with_time) if value else "—"


def _table(doc, headers: list[str], rows: list[list[str]]):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for i, header in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = header
        for run in cell.paragraphs[0].runs:
            run.bold = True
    for row in rows:
        cells = table.add_row().cells
        for i, value in enumerate(row):
            cells[i].text = str(value)
    doc.add_paragraph()


def _note(doc, text: str):
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.italic = True
    run.font.size = Pt(8.5)
    run.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def render_briefing_docx(briefing: dict) -> bytes:
    facts = briefing["facts"]
    content = briefing["content"]
    company = facts["company"]
    inv = facts["inventory"]
    insta = facts["instagram"] or {}

    doc = Document()
    doc.styles["Normal"].font.name = "Aptos"
    doc.styles["Normal"].font.size = Pt(10)

    title = doc.add_heading(f"{company['name'].upper()} — BRIEFING DE MARKETING", 0)
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p = doc.add_paragraph()
    p.add_run("Versão: ").bold = True
    p.add_run(f"v{briefing['version']} — gerado em {fmt_local(briefing['created_at'])} por {briefing.get('created_by') or '—'}")
    p.add_run("\nPeríodo analisado: ").bold = True
    p.add_run(f"{facts['period']['start_label']} a {facts['period']['end_label']}")
    p.add_run("\nDatas exibidas no fuso America/Sao_Paulo.").italic = True

    doc.add_heading("1. Resumo do estoque (fatos observados)", level=1)
    summary = inv.get("summary") or {}
    _table(doc, ["Indicador", "Valor"], [
        ["Veículos ativos na última coleta", num(inv.get("active_count"))],
        ["Anúncios já observados (total histórico)", num(inv.get("observed_total"))],
        ["Observados pela primeira vez no período", num(inv.get("new_in_period"))],
        ["Não encontrados na última coleta (no período)", num(inv.get("missing_in_period"))],
        ["Última coleta bem-sucedida", date(summary.get("last_success_at"), True)],
        ["Última coleta completa", date(summary.get("last_complete_at"), True)],
    ])
    _note(doc, "'Não encontrado na última coleta' não significa venda confirmada.")
    if inv.get("price_bands"):
        _table(doc, ["Faixa de preço", "Veículos"], [[b["band"], num(b["count"])] for b in inv["price_bands"]])

    doc.add_heading("2. Marcas e modelos mais presentes", level=1)
    _table(doc, ["Marca", "Qtd.", "Preço mín.", "Preço máx."],
           [[b["brand"], num(b["count"]), brl(b.get("price_min")), brl(b.get("price_max"))] for b in inv.get("by_brand", [])[:15]])
    _table(doc, ["Marca", "Modelo", "Qtd.", "Faixa de preço", "Categoria"],
           [[m["brand"], m["model"], num(m["count"]), f"{brl(m.get('price_min'))} — {brl(m.get('price_max'))}", m.get("content_category", "")]
            for m in inv.get("by_model", [])[:20]])

    doc.add_heading("3. Anúncios com maior tempo observado", level=1)
    _table(doc, ["Veículo", "Ano", "Preço", "Primeira observação", "Dias observado"],
           [[f"{v['brand']} {v['model']} {v.get('version') or ''}".strip(), str(v.get("year_model") or "—"), brl(v.get("price")),
             date(v.get("first_seen_at")), num(v.get("observed_days"))] for v in inv.get("longest_observed", [])])
    _note(doc, (inv.get("observed_days") or {}).get("note", ""))

    doc.add_heading("4. Alterações de preço observadas", level=1)
    changes = inv.get("price_changes") or []
    if changes:
        _table(doc, ["Data", "Veículo", "Antes", "Depois"],
               [[date(c["observed_at"]), f"{c.get('brand')} {c.get('model')}", brl(c.get("previous_price")), brl(c.get("price"))] for c in changes[:15]])
    else:
        doc.add_paragraph("Nenhuma alteração de preço observada no período.")

    doc.add_heading("5. Evolução do Instagram", level=1)
    if insta.get("status") in ("sem_perfil", "sem_dados"):
        doc.add_paragraph(insta.get("message", "Sem dados do Instagram."))
    else:
        latest = insta.get("latest") or {}
        growth = insta.get("growth") or {}
        posts = insta.get("posts_summary") or {}
        rows = [
            ["Perfil", f"@{insta.get('username')}"],
            ["Seguidores (última coleta válida)", f"{num(latest.get('followers'))} em {date(latest.get('collected_at'), True)}"],
        ]
        if growth.get("status") == "ok":
            rows.append(["Variação de seguidores",
                         f"{num(growth['absolute'])} ({num(growth.get('percent'), '%')}) entre "
                         f"{date(growth['start']['date'])} e {date(growth['end']['date'])}"])
        else:
            rows.append(["Variação de seguidores", "Histórico insuficiente"])
        rows += [
            ["Publicações no período", num(posts.get("count")) + (" (mínimo; amostra parcial)" if posts.get("count_is_lower_bound") else "")],
            ["Frequência", f"{num(posts.get('per_week'))} por semana"],
            ["Curtidas (média / mediana)", f"{num((posts.get('likes') or {}).get('mean'))} / {num((posts.get('likes') or {}).get('median'))} (n={(posts.get('likes') or {}).get('n', 0)})"],
            ["Comentários (média / mediana)", f"{num((posts.get('comments') or {}).get('mean'))} / {num((posts.get('comments') or {}).get('median'))} (n={(posts.get('comments') or {}).get('n', 0)})"],
            ["Interação pública estimada (mediana)", f"{num((posts.get('interaction') or {}).get('median'), '%')} (n={(posts.get('interaction') or {}).get('n', 0)})"],
        ]
        _table(doc, ["Indicador", "Valor"], rows)
        for warning in insta.get("warnings", []):
            _note(doc, "Aviso: " + warning)

        doc.add_heading("6. Publicações com maior interação visível", level=1)
        top = insta.get("top_posts") or []
        if top:
            _table(doc, ["Data", "Formato", "Legenda", "Curtidas", "Comentários", "Interação est.", "Link"],
                   [[date(p["taken_at"]), FORMAT_LABELS.get(p.get("format"), p.get("format") or "—"),
                     (p.get("caption") or "")[:80], num(p.get("likes")), num(p.get("comments")),
                     num((p.get("interaction") or {}).get("value"), "%"), p.get("url", "")] for p in top])
        else:
            doc.add_paragraph("Sem publicações com métricas visíveis no período.")

    doc.add_heading("7. Comparação com concorrentes", level=1)
    comp_rows = (facts.get("comparison") or {}).get("rows") or []
    if len(comp_rows) > 1:
        _table(doc, ["Empresa", "Seguidores", "Variação", "Posts/semana", "Interação mediana (n)", "Veículos ativos"],
               [[r["name"], num(r.get("followers")),
                 (f"{num((r.get('growth') or {}).get('percent'), '%')} ({date((r.get('growth') or {}).get('start', {}).get('date'))}–{date((r.get('growth') or {}).get('end', {}).get('date'))})"
                  if (r.get("growth") or {}).get("status") == "ok" else "histórico insuficiente"),
                 num((r.get("posts") or {}).get("per_week")),
                 f"{num((r.get('interaction') or {}).get('median'), '%')} ({(r.get('interaction') or {}).get('n', 0)})",
                 num((r.get("inventory") or {}).get("active_count"))] for r in comp_rows])
        for note in (facts.get("comparison") or {}).get("notes", []):
            _note(doc, note)
    else:
        doc.add_paragraph("Nenhum concorrente configurado para esta empresa.")

    doc.add_heading("8. Sugestões de pautas", level=1)
    for s in content.get("suggestions", []):
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(s["pauta"]).bold = True
        p.add_run(f"\nDado que motivou: {s['motivo']}")
    if not content.get("suggestions"):
        doc.add_paragraph("Sem dados suficientes para sugerir pautas automaticamente.")

    doc.add_heading("9. Hipóteses de testes de conteúdo", level=1)
    _note(doc, "Hipóteses, não conclusões: precisam ser testadas e medidas.")
    for h in content.get("hypotheses", []):
        p = doc.add_paragraph(style="List Bullet")
        p.add_run(h["hipotese"]).bold = True
        p.add_run(f"\nTeste: {h['teste']}\nComo medir: {h['metrica']}\nDado que motivou: {h['motivo']}")

    doc.add_heading("10. Perguntas para a reunião com o cliente", level=1)
    for q in content.get("questions", []):
        p = doc.add_paragraph(style="List Number")
        p.add_run(q["pergunta"])
        p.add_run(f" ({q['motivo']})").italic = True

    doc.add_heading("11. Dados adicionais necessários para avaliar resultados comerciais", level=1)
    for item in content.get("data_needed", []):
        doc.add_paragraph(item, style="List Bullet")

    doc.add_heading("12. Fontes e limitações", level=1)
    for src in content.get("sources", []):
        doc.add_paragraph(f"{src['name']}: {src.get('detail') or '—'} (última coleta bem-sucedida: {date(src.get('last_success_at'), True)})",
                          style="List Bullet")
    for item in content.get("limitations", []):
        doc.add_paragraph(item, style="List Bullet")

    buffer = io.BytesIO()
    doc.save(buffer)
    return buffer.getvalue()
