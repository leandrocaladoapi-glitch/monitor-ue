#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes das fontes oficiais da União Europeia (conectores regulatórios).

São testes de fiação/parse: usam amostras com o formato exato devolvido pelas
fontes oficiais (confirmado nas sondas de CI registradas em out/probe e nas
sondas manuais documentadas no README). Nenhum item é inventado no dataset —
as amostras aqui reproduzem apenas o formato dos payloads reais (título, data,
URL oficial) para provar que o coletor extrai exatamente esses campos.
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from sources import fontes_disponiveis, instanciar  # noqa: E402
from sources.base import (  # noqa: E402
    Canal, Fonte, ResultadoFonte, classificar_relevancia, parse_html_links,
    parse_rss, registrar, url_canonica,
)
from sources.eu_parsers import (  # noqa: E402
    parse_consilium_registro, parse_consultas_hys, parse_ep_procedimento,
    parse_ep_procedimentos, parse_eurlex_busca, parse_legislative_train,
)

ORGAOS_MONITORADOS = ["ai_office", "edpb", "edps", "eu_commission", "eu_council",
                      "eu_parliament", "eurlex"]

# ---------------------------------------------------------------- amostras
# Parlamento — API v2 (listagem), formato real (JSON-LD; sonda 18/09/2026)
EP_LISTA = {
    "@context": "https://data.europarl.europa.eu/api/v2/core-context.jsonld",
    "data": [
        {"id": "eli/dl/proc/2024-2526", "type": "Process",
         "process_id": "2024-2526", "process_type": "RSP",
         "label": "2024/2526(RSP)"},
    ],
    "searchResults": {"hits": 10000},
    "meta": {"total": 10000},
}

# Parlamento — ficha do AI Act (consists_of; sonda 18/09/2026)
EP_FICHA = {
    "data": [{
        "id": "eli/dl/proc/2021-0106",
        "process_id": "2021-0106",
        "process_type": "COD",
        "label": "2021/0106(COD)",
        "title": "Regulation laying down harmonised rules on artificial intelligence",
        "consists_of": [
            {"id": "eli/dl/event/2021-06-07_210106COD", "activity_date": "2021-06-07",
             "activity_id": "REFERRAL_210106COD_20210607",
             "had_activity_type": "http://data.europarl.europa.eu/def/ep-activities/REFERRAL",
             "occured_at_stage": "http://data.europarl.europa.eu/def/procedure-phase/RDG1"},
            {"id": "eli/dl/event/2024-03-13_210106COD", "activity_date": "2024-03-13",
             "activity_id": "PLENARY_210106COD_20240313",
             "had_activity_type": "http://data.europarl.europa.eu/def/ep-activities/PLENARY_VOTE",
             "occured_at_stage": "http://data.europarl.europa.eu/def/procedure-phase/RDG1",
             "decided_on_a_realization_of": ["TA-9-2024-0138"]},
            {"id": "eli/dl/event/2024-07-12_210106COD", "activity_date": "2024-07-12",
             "activity_id": "OJ_210106COD_20240712",
             "had_activity_type":
                 "http://data.europarl.europa.eu/def/ep-activities/PUBLICATION_OFFICIAL_JOURNAL"},
        ],
    }],
}

# EUR-Lex — bloco de resultado da busca oficial (formato real)
EURLEX_HTML = """<html><body>
<div class="row">
<h2><a class="title" href="https://eur-lex.europa.eu/legal-content/EN/AUTO/?uri=CELEX:32024R1689&amp;qid=1">Regulation (EU) 2024/1689 of 13 June 2024 laying down harmonised rules on artificial intelligence (Artificial Intelligence Act)</a></h2>
<div class="tt_page">CELEX number: 32024R1689</div>
<div class="tt_page">Date of document: 12/07/2024;</div>
<div class="tt_page">OJ L, 12.7.2024</div>
<div class="tt_page">Latest consolidated version: [12/07/2024](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727)</div>
</div>
</body></html>"""

# Conselho — item do registro público (formato real, server-rendered)
CONSILIUM_HTML = """<html><body>
<div class="doc-item">
<a href="https://data.consilium.europa.eu/doc/document/ST-5663-2025-INIT/en/pdf">
Proposal for a Regulation on harmonised rules on artificial intelligence</a>
<table><tr><td>Subject matters:</td><td>DATAPROTECT</td></tr>
<tr><td>Interinstitutional file:</td><td>2021/0106(COD)</td></tr>
<tr><td>Date of meeting</td><td>25/09/2025</td></tr></table>
</div>
</body></html>"""

# Comissão — item do Have Your Say (formato real, server-rendered)
HYS_HTML = """<html><body>
<div class="initiative">
<a href="/have-your-say/initiatives/16155-EHDS-technical-requirements-for-HealthDataEU_implementing-regulation_en">
EHDS technical requirements for HealthData@EU implementing regulation</a>
<div>Call for evidence: Open</div>
<div>Feedback period 01 September 2026 - 29 September 2026</div>
<div>Type of act Implementing regulation</div>
</div>
</body></html>"""

# AI Office — item do newsroom digital-strategy (formato real)
DS_HTML = """<html><body>
<div class="views-row">
<a href="/en/news/commission-starts-enforcing-ai-act-rules-and-new-transparency-requirements-2-august">Commission starts enforcing AI Act rules and new transparency requirements on 2 August</a>
<span>31 July 2026</span>
</div>
</body></html>"""

# EDPB — RSS oficial (formato real)
EDPB_RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>EDPB News</title>
<item>
  <title>Press release: CNIL fines EXTIA</title>
  <link>https://www.edpb.europa.eu/system/files/2026-09/cnil_press_release_en.pdf</link>
  <guid isPermaLink="false">2d4a86a3-9d2c-4c7e-9f4e-20260911</guid>
  <pubDate>Fri, 11 Sep 2026 12:00:00 +0000</pubDate>
  <description><![CDATA[The CNIL fined EXTIA EUR 300 000 for failures on data subject rights (art. 12 and 17 GDPR).]]></description>
</item>
</channel></rss>"""

# Legislative Train — item de tema (formato real)
TRAIN_HTML = """<html><body>
<div class="carriage">
<a href="/legislative-train/theme-a-europe-fit-for-the-digital-age/file-artificial-intelligence-act">Artificial Intelligence Act</a>
<div>Status: Provisional agreement approved by the committees</div>
</div>
</body></html>"""


class ParserTests(unittest.TestCase):
    """Cada parser tem de extrair título, data e URL oficial — nada além."""

    def test_ep_listagem(self):
        itens = parse_ep_procedimentos(EP_LISTA)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["process_id"], "2024-2526")
        self.assertIn("2024/2526(RSP)", item["titulo"])
        self.assertTrue(item["link"].startswith("https://data.europarl.europa.eu/"))

    def test_ep_ficha_ai_act(self):
        f = parse_ep_procedimento(EP_FICHA, proc_id="2021-0106")
        self.assertEqual(f["process_id"], "2021-0106")
        self.assertEqual(f["process_type"], "COD")
        datas = [e["data"] for e in f["eventos"]]
        self.assertEqual(datas, sorted(datas))  # eventos ordenados por data
        tipos = {e["tipo"] for e in f["eventos"]}
        self.assertIn("PLENARY_VOTE", tipos)
        self.assertIn("PUBLICATION_OFFICIAL_JOURNAL", tipos)
        voto = [e for e in f["eventos"] if e["tipo"] == "PLENARY_VOTE"][0]
        self.assertEqual(voto["docs"], ["TA-9-2024-0138"])

    def test_eurlex_busca(self):
        itens = parse_eurlex_busca(EURLEX_HTML)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["celex"], "32024R1689")
        self.assertEqual(item["data"], "2024-07-12")
        self.assertIn("Artificial Intelligence Act", item["titulo"])
        self.assertEqual(item["url_consolidada"],
                         "https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX:02024R1689-20260727")

    def test_consilium_registro(self):
        itens = parse_consilium_registro(CONSILIUM_HTML)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["doc_id"], "ST-5663-2025-INIT")
        self.assertEqual(item["arquivo_interinstitucional"], "2021/0106(COD)")
        self.assertEqual(item["data"], "2025-09-25")
        self.assertTrue(item["link"].startswith("https://data.consilium.europa.eu/"))

    def test_hys_consulta(self):
        itens = parse_consultas_hys(HYS_HTML)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["consulta_id"], "16155")
        self.assertEqual(item["periodo_feedback"], "2026-09-01 → 2026-09-29")
        self.assertEqual(item["estagio"], "Call for evidence")
        self.assertEqual(item["tipo_ato"], "Implementing regulation")

    def test_digital_strategy(self):
        itens = parse_html_links(DS_HTML, "https://digital-strategy.ec.europa.eu",
                                 r"/en/news/[a-z0-9\-]{8,}")
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertIn("AI Act", item["titulo"])
        self.assertEqual(item["data"], "2026-07-31")

    def test_edpb_rss(self):
        item = parse_rss(EDPB_RSS)[0]
        self.assertIn("EXTIA", item["titulo"])
        self.assertEqual(item["data"], "2026-09-11")
        self.assertTrue(item["link"].startswith("https://www.edpb.europa.eu/"))

    def test_legislative_train(self):
        itens = parse_legislative_train(TRAIN_HTML)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertEqual(item["titulo"], "Artificial Intelligence Act")
        self.assertIn("file-artificial-intelligence-act", item["link"])

    def test_url_canonica_iguala_variacoes(self):
        self.assertEqual(url_canonica("https://WWW.exemplo.europa.eu/a/1/?utm=2#x"),
                         url_canonica("http://exemplo.europa.eu/a/1"))

    def test_classificacao_conservadora_sigla_ai_isolada(self):
        # A sigla isolada "AI" NÃO é sinal forte (falso positivo em inglês)
        self.assertEqual(classificar_relevancia("Improvement of a company's sales pipeline said to grow"), None)
        self.assertEqual(classificar_relevancia(
            "Commission publishes guidelines on the AI Act and general-purpose AI models"), "forte")
        self.assertEqual(classificar_relevancia("Digital transformation report"), "revisar")


class _CtxFalso:
    def expirado(self, folga=0.0):
        return False

    def checar(self, folga=0.0):
        return None

    def log(self, *a, **k):
        return None


@registrar
class _FonteDeTeste(Fonte):
    """Fonte artificial só para exercitar o núcleo (não entra no monitoramento)."""
    orgao = "teste_dedup"
    nome = "Fonte de teste (dedup)"
    canais = [Canal("p1", "https://exemplo.europa.eu/x"),
              Canal("p2", "https://exemplo.europa.eu/x")]

    def _coletar_canal(self, ctx, canal):
        return self._pos_processar([
            {"titulo": "Comunicado sobre inteligência artificial",
             "link": "https://exemplo.europa.eu/a/1", "data": "2026-09-17"},
            {"titulo": "Comunicado sobre inteligência artificial (eco)",
             "link": "https://exemplo.europa.eu/a/1/?pagina=2", "data": "2026-09-17"},
            {"titulo": "Comunicado de rotina administrativa",
             "link": "https://exemplo.europa.eu/a/2", "data": "2026-09-16"},
        ], canal)


class DedupTests(unittest.TestCase):
    def test_mesma_url_em_dois_canais_conta_uma_vez(self):
        fonte = _FonteDeTeste()
        resultado = ResultadoFonte("teste_dedup", "Fonte de teste")
        fonte.coletar(_CtxFalso(), resultado)
        self.assertEqual(len(resultado.itens), 1)
        self.assertEqual(resultado.itens_duplicados, 4)   # 1 eco + eco dos 3 no 2º canal
        self.assertEqual(resultado.itens_descartados, 1)  # comunicado sem tema
        self.assertEqual(resultado.como_dict()["itens_duplicados"], 4)
        self.assertEqual(resultado.status, "ok")


class RodapeAtosTests(unittest.TestCase):
    """O rodapé do site só anuncia o atos.json quando o dataset existe — e
    sempre com o domínio vigente na hora do build (build_site.py troca de
    domínio depois de importar o módulo; um valor congelado no import
    publicaria o domínio antigo e bloquearia o build)."""

    def setUp(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import build_site_core as core  # noqa: PLC0415
        self.core = core
        self._base, self._site = core.BASE, core.SITE_URL

    def tearDown(self):
        self.core.BASE, self.core.SITE_URL = self._base, self._site

    def _preparar(self, com_atos):
        tmp = tempfile.mkdtemp(prefix="rodape_")
        self.addCleanup(shutil.rmtree, tmp, True)
        os.makedirs(os.path.join(tmp, "data", "legislation"), exist_ok=True)
        if com_atos:
            with open(os.path.join(tmp, "data", "legislation", "atos.json"), "w",
                      encoding="utf-8") as f:
                f.write("{}")
        self.core.BASE = tmp
        self.core.SITE_URL = "https://dominio-oficial.test"
        return tmp

    def test_sem_dataset_nao_ha_link(self):
        self._preparar(com_atos=False)
        self.assertEqual(self.core._atos_footer_link(), "")
        self.assertNotIn("atos.json", self.core.page("t", "d", "index.html", "corpo"))

    def test_com_dataset_o_link_usa_o_dominio_do_build(self):
        self._preparar(com_atos=True)
        link = self.core._atos_footer_link()
        self.assertIn("https://dominio-oficial.test/data/atos.json", link)
        html = self.core.page("t", "d", "index.html", "corpo")
        self.assertIn("https://dominio-oficial.test/data/atos.json", html)
        self.assertNotIn("monitor-legislativo-five.vercel.app", html)


class ContratoDasFontesTests(unittest.TestCase):
    """Contratos mínimos que a missão exige de cada instituição monitorada."""

    def test_todas_as_instituicoes_registradas(self):
        registrados = fontes_disponiveis()
        for orgao in ORGAOS_MONITORADOS:
            self.assertIn(orgao, registrados)

    def test_cada_instituicao_tem_canal_obrigatorio_e_url_oficial(self):
        dominios = {
            "ai_office": ("digital-strategy.ec.europa.eu", "ec.europa.eu"),
            "edpb": ("edpb.europa.eu",),
            "edps": ("edps.europa.eu",),
            "eu_commission": ("ec.europa.eu", "commission.europa.eu"),
            "eu_council": ("consilium.europa.eu", "data.consilium.europa.eu"),
            "eu_parliament": ("europarl.europa.eu", "data.europarl.europa.eu"),
            "eurlex": ("eur-lex.europa.eu",),
        }
        for orgao in ORGAOS_MONITORADOS:
            fonte = instanciar(orgao, logger=lambda *a, **k: None)
            self.assertTrue(fonte.canais, f"{orgao} sem canais")
            self.assertTrue(any(c.obrigatorio for c in fonte.canais),
                            f"{orgao} sem canal obrigatório")
            urls = [c.url for c in fonte.canais] + [c.url_template for c in fonte.canais
                                                    if c.url_template]
            for url in urls:
                self.assertTrue(
                    any(d in url for d in dominios[orgao]),
                    f"{orgao}: canal fora dos domínios oficiais ({url})")

    def test_urls_ascii(self):
        """URLs geradas precisam ser ASCII (sem acento cru — bug clássico)."""
        for orgao in ORGAOS_MONITORADOS:
            fonte = instanciar(orgao, logger=lambda *a, **k: None)
            for canal in fonte.canais:
                for _topico, url in canal.urls():
                    url.encode("ascii")

    def test_fonte_obrigatoria_do_monitor(self):
        """As 7 instituições são obrigatórias (nada do monitor é opcional)."""
        for orgao in ORGAOS_MONITORADOS:
            fonte = instanciar(orgao, logger=lambda *a, **k: None)
            self.assertTrue(fonte.obrigatoria, orgao)

    def test_eu_parliament_cobre_canais_exigidos(self):
        """Parlamento: API v2, busca, Legislative Train e imprensa oficial."""
        fonte = instanciar("eu_parliament", logger=lambda *a, **k: None)
        rotulos = " | ".join(c.rotulo for c in fonte.canais)
        for exigido in ("API v2", "Legislative Train", "sala de imprensa"):
            self.assertIn(exigido, rotulos)

    def test_eurlex_cobre_busca_e_jo(self):
        fonte = instanciar("eurlex", logger=lambda *a, **k: None)
        rotulos = " | ".join(c.rotulo for c in fonte.canais)
        self.assertIn("busca por tema", rotulos)
        self.assertIn("Jornal Oficial", rotulos)


if __name__ == "__main__":
    unittest.main(verbosity=2)
