# Análise do scraper original (`azul_premium_scraper.zip`)

Cópia de referência dos arquivos-fonte do projeto original. Não foram copiados `.venv/`,
`__pycache__/`, `output/` nem o arquivo temporário `~$iefing_azul_premium.docx`.

## Estrutura encontrada

| Arquivo | Conteúdo |
|---|---|
| `automation.py` | Script único (1.313 linhas): coleta, parsers, rankings, exportação CSV/JSON/XLSX e briefing DOCX |
| `config.json` / `config.example.json` | Idênticos; 3 empresas (Azul `azul`, Hazul `hazul`, Avance `playwright` + `load_more`) |
| `README.md` | Instruções de instalação/uso |
| `output/<empresa>/` | Exemplos gerados em 25/09/2026 (estoque, rankings, briefing, `coleta_info.json`) |
| `DOCUMENTACAO_MULTIEMPRESA.docx` | Documentação em Word |

## Inconsistências
- O README manda executar `python azul_premium_scraper.py`, mas o script se chama `automation.py`
  (o `__pycache__` contém `azul_premium_scraper.cpython-313.pyc`, sinal de renomeação).
- `config.example.json` é igual ao `config.json` (sem valores de exemplo distintos).
- `COUNT_RE` ("N veículos encontrados") é declarado e nunca usado.
- O parâmetro `output_dir` de `playwright_html` não é usado; a captura de diagnóstico abre o navegador uma segunda vez.

## Comportamento verificado contra os sites em 30/10/2026
| Site | Original | Novo parser |
|---|---|---|
| Azul Premium | 100 de 102 anunciados — descarta marcas fora da lista fixa (OMODA, TROLLER) | 102/102, marca lida da estrutura do card, ID do anúncio extraído do link |
| Grupo Hazul | 3 de 6 — não reconhece "CITROËN" (trema); grava o card inteiro em `modelo`; sem link | 6/6, modelo via JSON-LD, ID e link do anúncio |
| Avance Premium | HTML estático sem veículos; com Playwright, grava o card inteiro em `modelo` (ver `output/avance_premium/estoque.csv`) | Lê o mesmo endpoint `admin-ajax.php` (`filtrar_estoque`) usado pela página; 26/26 com total anunciado |

Outros pontos do original tratados no novo projeto:
- `parse_hazul` fazia `text.split("  ")` após `clean_text` (que já colapsa espaços), então nunca separava linhas.
- O `load_more` clicava também em "ver mais" — texto usado nos links de detalhe dos veículos, podendo navegar para fora da listagem.
- Não havia proteção contra URLs internas (SSRF), nem distinção entre coleta parcial e completa.
- A deduplicação incluía preço na chave, o que impediria rastrear alterações de preço.

## O que foi reaproveitado
- Expressões de preço/ano/km, normalização de texto e lista de marcas (ampliada) → `backend/app/services/inventory/normalize.py`.
- Heurística genérica (`parse_azul`/`parse_hazul`) → `parsers/generic.py` (para sites sem parser dedicado).
- Fluxo Playwright com "carregar mais" → `fetchers.BrowserFetcher` (com bloqueio de destinos internos).
- Rankings por marca/modelo e as categorias de conteúdo (`Giro de estoque`, `Hero car / Premium`, `Custo-benefício`, `Oportunidade`) → `metrics/inventory.py`.
- Exportação CSV (UTF-8 com BOM) e XLSX com abas de estoque e rankings → `services/exports.py`.
- Estilo e seções do briefing DOCX → `services/briefing/docx_export.py` (ampliado).
