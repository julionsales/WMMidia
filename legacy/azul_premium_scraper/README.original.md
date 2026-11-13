# Scraper Multiempresa de Estoque

## Instalação

```powershell
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
```

## Configuração

Edite `config.json`. Cada empresa deve ter `nome`, `url`, `parser` e `min_model_stock`.

Parsers disponíveis:
- `azul`: Azul Premium
- `hazul`: Grupo Hazul
- `playwright`: sites que carregam estoque via JavaScript
- `requests`: páginas estáticas
- `auto`: escolhe pelo domínio conhecido ou usa requests como fallback

## Rodar

```powershell
python azul_premium_scraper.py
```

Com logs:
```powershell
python azul_premium_scraper.py --debug
```

## Saída

Cada empresa recebe sua própria pasta:

```text
output/
├── azul_premium/
├── grupo_hazul/
└── avance_premium/
```

Cada pasta contém CSV, JSON, Excel e briefing DOCX.

## Observação

Os sites de terceiros podem alterar HTML, filtros ou endpoints. O campo `parser` permite manter adaptações por site sem alterar o restante do pipeline.
