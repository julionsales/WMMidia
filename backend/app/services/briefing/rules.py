"""Regras transparentes para sugestões do briefing (sem IA paga).

Cada item informa o dado que o motivou. Pautas partem de FATOS observados; testes de
conteúdo são HIPÓTESES a validar. Nenhuma regra afirma que seguidores ou curtidas
geram vendas, nem associa publicações a veículos sem associação manual.
"""

from __future__ import annotations


def _brl(value) -> str:
    if value is None:
        return "sob consulta"
    return f"R$ {value:,.0f}".replace(",", ".")


def content_suggestions(facts: dict) -> list[dict]:
    inv = facts.get("inventory") or {}
    out: list[dict] = []
    models = inv.get("by_model") or []
    min_stock = facts.get("company", {}).get("min_model_stock", 3)

    giro = [m for m in models if m["count"] >= min_stock][:3]
    for m in giro:
        out.append({
            "pauta": f"Série 'Giro de estoque' com {m['brand']} {m['model']}",
            "motivo": f"{m['count']} unidades ativas observadas (regra: ≥ {min_stock} unidades do mesmo modelo).",
            "tipo": "fato_observado",
        })
    hero = [m for m in models if (m.get("price_min") or 0) >= 400_000][:2]
    for m in hero:
        out.append({
            "pauta": f"Conteúdo 'Hero car' destacando {m['brand']} {m['model']}",
            "motivo": f"Preço a partir de {_brl(m['price_min'])} (regra: ≥ R$ 400 mil).",
            "tipo": "fato_observado",
        })
    value = sorted([m for m in models if m.get("price_min") and m["price_min"] <= 180_000], key=lambda m: m["price_min"])[:2]
    for m in value:
        out.append({
            "pauta": f"Custo-benefício: {m['brand']} {m['model']} a partir de {_brl(m['price_min'])}",
            "motivo": "Modelo com preço inicial até R$ 180 mil (regra herdada do briefing original).",
            "tipo": "fato_observado",
        })
    reductions = [c for c in inv.get("price_changes") or [] if c.get("delta") is not None and c["delta"] < 0][:3]
    for c in reductions:
        out.append({
            "pauta": f"Oportunidade: {c.get('brand')} {c.get('model')} com preço reduzido",
            "motivo": f"Preço observado caiu de {_brl(c['previous_price'])} para {_brl(c['price'])} "
                      f"em {c['observed_at'][:10]}. Confirmar condição com o cliente antes de divulgar.",
            "tipo": "fato_observado",
        })
    if inv.get("new_in_period"):
        out.append({
            "pauta": "Chegadas recentes ao estoque",
            "motivo": f"{inv['new_in_period']} anúncio(s) observados pela primeira vez no período.",
            "tipo": "fato_observado",
        })
    long_ones = [v for v in inv.get("longest_observed") or [] if (v.get("observed_days") or 0) >= 45][:3]
    if long_ones:
        names = ", ".join(f"{v['brand']} {v['model']}" for v in long_ones)
        out.append({
            "pauta": f"Dar visibilidade a anúncios observados há mais tempo ({names})",
            "motivo": "Anúncios presentes em coletas há ≥ 45 dias. Tempo observado não é tempo real de estoque.",
            "tipo": "fato_observado",
        })
    return out


def test_hypotheses(facts: dict) -> list[dict]:
    insta = facts.get("instagram") or {}
    summary = insta.get("posts_summary") or {}
    out: list[dict] = []
    perf = [f for f in insta.get("format_performance") or [] if f["n"] >= 3]
    if len(perf) >= 2:
        best = max(perf, key=lambda f: f["median"])
        worst = min(perf, key=lambda f: f["median"])
        if best["format"] != worst["format"]:
            out.append({
                "hipotese": f"Publicações em formato '{best['format']}' tendem a ter mais interação visível que '{worst['format']}'.",
                "teste": f"Nas próximas 4 semanas, aumentar a proporção de '{best['format']}' mantendo temas comparáveis.",
                "metrica": "Mediana da interação pública estimada por formato (com n ≥ 3 em cada grupo).",
                "motivo": f"Mediana observada: {best['format']} {best['median']}% (n={best['n']}) vs. "
                          f"{worst['format']} {worst['median']}% (n={worst['n']}). Amostra pequena; não é causalidade.",
            })
    per_week = summary.get("per_week")
    comp_rates = [r["posts"]["per_week"] for r in (facts.get("comparison") or {}).get("rows", [])[1:]
                  if r.get("posts", {}).get("per_week") is not None]
    if per_week is not None and comp_rates:
        median_comp = sorted(comp_rates)[len(comp_rates) // 2]
        if per_week < median_comp:
            out.append({
                "hipotese": "Uma frequência de publicação mais regular pode ampliar a presença do perfil.",
                "teste": f"Testar {round(median_comp)} publicações/semana por 4 semanas.",
                "metrica": "Variação de seguidores entre coletas e interação estimada por publicação.",
                "motivo": f"Frequência observada {per_week}/semana vs. mediana dos concorrentes selecionados {median_comp}/semana"
                          + (" (amostra parcial de publicações)" if summary.get("count_is_lower_bound") else "") + ".",
            })
    if (facts.get("inventory") or {}).get("by_model"):
        out.append({
            "hipotese": "Publicações sobre modelos com mais unidades em estoque podem ter efeito comercial maior.",
            "teste": "Associar manualmente publicações a anúncios e comparar com leads/atendimentos do período.",
            "metrica": "Leads e atendimentos por modelo (dados do cliente/CRM), não curtidas.",
            "motivo": "Hoje há apenas dados públicos; sem dados de leads não é possível medir resultado comercial.",
        })
    return out


def meeting_questions(facts: dict) -> list[dict]:
    inv = facts.get("inventory") or {}
    insta = facts.get("instagram") or {}
    questions = [
        {"pergunta": "Quais canais geram mais leads hoje (site, WhatsApp, Instagram, portais)?", "motivo": "Sem dados de leads não há como avaliar resultado comercial do conteúdo."},
        {"pergunta": "Quais modelos a loja quer priorizar no próximo mês (margem, giro, campanhas)?", "motivo": "Prioridade comercial não é observável nos dados públicos."},
    ]
    if inv.get("missing_in_period"):
        questions.append({
            "pergunta": f"{inv['missing_in_period']} anúncio(s) deixaram de aparecer no período: foram vendidos, reservados ou retirados?",
            "motivo": "Ausência no site não confirma venda.",
        })
    if any((v.get("observed_days") or 0) >= 45 for v in inv.get("longest_observed") or []):
        questions.append({"pergunta": "Há condição especial para os veículos observados há mais tempo?", "motivo": "Anúncios com tempo observado ≥ 45 dias."})
    if insta.get("status") not in (None, "ok"):
        questions.append({"pergunta": "O perfil do Instagram informado está correto e é público?", "motivo": f"Situação da coleta: {insta.get('status')}."})
    if (insta.get("posts_summary") or {}).get("posts_without_metrics"):
        questions.append({"pergunta": "O perfil oculta curtidas? Vocês podem compartilhar os insights da conta?", "motivo": "Há publicações sem métricas públicas."})
    return questions


DATA_NEEDED = [
    "Leads por origem (site, WhatsApp, Instagram, portais) e por veículo/modelo.",
    "Orçamentos e propostas emitidos no período.",
    "Vendas efetivadas, com data e veículo.",
    "Insights da conta do Instagram (alcance, salvamentos, compartilhamentos, visitas) via acesso autorizado.",
    "Investimento em mídia paga e UTMs dos links divulgados.",
]

LIMITATIONS = [
    "Dados públicos coletados automaticamente; podem estar incompletos ou desatualizados.",
    "Seguidores e curtidas não comprovam vendas nem intenção de compra.",
    "Interação pública estimada = (curtidas + comentários) / seguidores × 100; não é engajamento por alcance.",
    "Publicações sem métricas visíveis ficam fora das médias; o tamanho da amostra (n) é informado.",
    "Crescimento usa apenas datas de coletas reais; não há histórico anterior ao início do monitoramento.",
    "'Não encontrado na última coleta' não significa venda confirmada.",
    "Tempo observado no estoque vai da primeira à última coleta em que o anúncio apareceu.",
    "Publicações só são associadas a veículos quando a equipe faz a associação manual.",
]
