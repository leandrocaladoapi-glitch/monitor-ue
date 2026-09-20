#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Testes das fontes oficiais multiórgão (ANPD, CNJ, TSE, DOU, Planalto, MCTI).

São testes de fiação/parse: usam amostras com o formato exato devolvido pelas
APIs oficiais (confirmado nas sondas de CI registradas em out/probe). Nenhum
item é inventado no dataset — as amostras aqui reproduzem apenas o formato dos
payloads reais (título, data, URL oficial, ementa) para provar que o coletor
extrai exatamente esses campos.
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
    Canal, Fonte, ResultadoFonte, classificar_relevancia, parse_cnj_atos,
    parse_dou_embutido, parse_plone_search, parse_rss, registrar, url_canonica,
)

ORGAOS_MONITORADOS = ["anpd", "cnj", "tse", "dou", "planalto", "mcti"]

# ---------------------------------------------------------------- amostras
# ANPD — plone.restapi @search (portal_type=News Item)
ANPD_JSON = {
    "items_total": 288,
    "items": [
        {
            "@id": "https://www.gov.br/anpd/pt-br/assuntos/noticias/anpd-publica-"
                   "resolucao-sobre-ia",
            "@type": "News Item",
            "title": "ANPD publica resolução sobre uso de inteligência artificial",
            "description": "Norma trata de governança de IA e proteção de dados.",
            "effective": "2026-09-16T18:00:00-03:00",
        }
    ],
}

# TSE — plone.restapi @search (portal_type=Noticia e path=/legislacao)
TSE_NOTICIA_JSON = {
    "items_total": 18650,
    "items": [
        {
            "@id": "https://www.tse.jus.br/comunicacao/noticias/2026/Setembro/"
                   "tse-lanca-projeto-meu-primeiro-confirma-para-engajar-jovens-eleitores-no-df",
            "@type": "Noticia",
            "title": "TSE lança projeto \"Meu Primeiro Confirma\" para engajar jovens eleitores no DF",
            "description": "Ação-piloto com estudantes de 16 e 17 anos promoveu experiência.",
            "effective": "2026-09-17T16:36:00+00:00",
        }
    ],
}
TSE_ATO_JSON = {
    "items_total": 21226,
    "items": [
        {
            "@id": "https://www.tse.jus.br/legislacao/compilada/prt/2026/"
                   "portaria-no-623-de-15-de-setembro-de-2026",
            "@type": "Ato",
            "title": "PORTARIA Nº 623, DE 15 DE SETEMBRO DE 2026",
            "description": "",
            "effective": "2026-09-17T12:09:37+00:00",
        }
    ],
}

# CNJ — API oficial do Sistema de Atos Normativos
CNJ_ATOS_JSON = {
    "total": 6695,
    "data": [
        {
            "id": 7034,
            "tipo": "Portaria",
            "numero": "420",
            "data_publicacao": "2026-09-08",
            "situacao": "Vigente",
            "ementa": "Altera a Portaria Presidência nº 123 e dá outras providências.",
            "url_ato": "https://atos.cnj.jus.br/atos/detalhar/7034",
        }
    ],
}

# CNJ — API de conteúdo do portal (WordPress REST)
CNJ_WP_JSON = [
    {
        "id": 123456,
        "date": "2026-09-11T10:00:00",
        "link": "https://www.cnj.jus.br/inteligencia-artificial-e-tema-de-debate-no-para/",
        "title": {"rendered": "Inteligência artificial é tema de debate no Pará"},
        "excerpt": {"rendered": "<p>Encontro discutiu governança de IA no Judiciário.</p>"},
        "type": "post",
    }
]

# DOU — bloco JSON embutido na busca oficial do in.gov.br
DOU_HTML = (
    '<html><body><script id="BuscaDouPortlet_params" type="application/json">'
    '{"jsonArray": [{"title": "DECRETO Nº 12.345, DE 17 DE SETEMBRO DE 2026",'
    ' "urlTitle": "decreto-n-12-345-de-17-de-setembro-de-2026",'
    ' "pubDate": "17/09/2026", "artType": "Decreto",'
    ' "hierarchyStr": "Atos do Poder Executivo/Presidência da República",'
    ' "content": "Dispõe sobre governança de inteligência artificial."}]}'
    '</script></body></html>'
)

# Planalto / MCTI — RSS oficial (Atom)
RSS_ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Notícias do Planalto</title>
  <entry>
    <title>Presidente sanciona lei de inteligência artificial</title>
    <link href="https://www.gov.br/planalto/pt-br/acompanhe-o-planalto/noticias/"
          rel="alternate" type="text/html"/>
    <updated>2026-09-17T12:00:00-03:00</updated>
    <summary>Sancionada a lei que trata de sistemas de IA.</summary>
  </entry>
</feed>"""


class ParserTests(unittest.TestCase):
    """Cada parser tem de extrair título, data e URL oficial — nada além."""

    def test_plone_search_anpd(self):
        itens = parse_plone_search(ANPD_JSON)
        self.assertEqual(len(itens), 1)
        item = itens[0]
        self.assertIn("inteligência artificial", item["titulo"])
        self.assertEqual(item["data"], "2026-09-16")
        self.assertTrue(item["link"].startswith("https://www.gov.br/anpd/"))

    def test_plone_search_tse(self):
        noticia = parse_plone_search(TSE_NOTICIA_JSON)[0]
        ato = parse_plone_search(TSE_ATO_JSON)[0]
        self.assertTrue(noticia["link"].startswith("https://www.tse.jus.br/comunicacao/noticias/"))
        self.assertEqual(noticia["tipo_ato"], "Noticia")
        self.assertEqual(ato["data"], "2026-09-17")
        self.assertEqual(ato["tipo_ato"], "Ato")
        self.assertIn("/legislacao/compilada/", ato["link"])

    def test_cnj_atos(self):
        item = parse_cnj_atos(CNJ_ATOS_JSON)[0]
        self.assertEqual(item["titulo"], "Portaria CNJ nº 420")
        self.assertEqual(item["link"], "https://atos.cnj.jus.br/atos/detalhar/7034")
        self.assertEqual(item["data"], "2026-09-08")
        self.assertIn("Situação: Vigente", item["descricao"])

    def test_cnj_wp_json(self):
        item = Fonte._parse_wp_json(CNJ_WP_JSON)[0]
        self.assertEqual(item["titulo"], "Inteligência artificial é tema de debate no Pará")
        self.assertEqual(item["data"], "2026-09-11")
        self.assertTrue(item["link"].startswith("https://www.cnj.jus.br/"))

    def test_dou_embutido(self):
        item = parse_dou_embutido(DOU_HTML)[0]
        self.assertEqual(item["titulo"], "DECRETO Nº 12.345, DE 17 DE SETEMBRO DE 2026")
        self.assertEqual(item["link"], "https://www.in.gov.br/web/dou/-/"
                                      "decreto-n-12-345-de-17-de-setembro-de-2026")
        self.assertEqual(item["data"], "2026-09-17")
        self.assertEqual(item["tipo_ato"], "Decreto")
        self.assertIn("Presidência da República", item["hierarquia"])

    def test_rss_atom(self):
        item = parse_rss(RSS_ATOM)[0]
        self.assertIn("inteligência artificial", item["titulo"])
        self.assertTrue(item["link"].startswith("https://www.gov.br/planalto/"))
        self.assertEqual(item["data"], "2026-09-17")

    def test_url_canonica_iguala_variacoes(self):
        self.assertEqual(url_canonica("https://WWW.exemplo.gov.br/a/1/?utm=2#x"),
                         url_canonica("http://exemplo.gov.br/a/1"))

    def test_classificacao_conservadora(self):
        self.assertEqual(classificar_relevancia("Aviso de manutenção do sistema"), None)
        self.assertEqual(classificar_relevancia("Sistema de governança e automação"), "forte")
        self.assertEqual(classificar_relevancia("Investimento em tecnologia"), "revisar")


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
    canais = [Canal("p1", "https://exemplo.gov.br/x"), Canal("p2", "https://exemplo.gov.br/x")]

    def _coletar_canal(self, ctx, canal):
        return self._pos_processar([
            {"titulo": "Resolução sobre inteligência artificial",
             "link": "https://exemplo.gov.br/a/1", "data": "2026-09-17"},
            {"titulo": "Resolução sobre inteligência artificial (eco)",
             "link": "https://exemplo.gov.br/a/1/?pagina=2", "data": "2026-09-17"},
            {"titulo": "Comunicado de rotina administrativa",
             "link": "https://exemplo.gov.br/a/2", "data": "2026-09-16"},
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
    """Contratos mínimos que a missão exige de cada órgão monitorado."""

    def test_todos_os_orgaos_registrados(self):
        registrados = fontes_disponiveis()
        for orgao in ORGAOS_MONITORADOS:
            self.assertIn(orgao, registrados)

    def test_cada_orgao_tem_canal_obrigatorio_e_url_oficial(self):
        dominios = {
            "anpd": ("gov.br/anpd",),
            "cnj": ("cnj.jus.br",),
            "tse": ("tse.jus.br", "in.gov.br"),
            "dou": ("in.gov.br",),
            "planalto": ("gov.br/planalto", "in.gov.br"),
            "mcti": ("gov.br/mcti", "in.gov.br"),
        }
        for orgao in ORGAOS_MONITORADOS:
            fonte = instanciar(orgao, logger=lambda *a, **k: None)
            self.assertTrue(fonte.canais, f"{orgao} sem canais")
            self.assertTrue(any(c.obrigatorio for c in fonte.canais),
                            f"{orgao} sem canal obrigatório")
            urls = [c.url for c in fonte.canais]
            for url in urls:
                self.assertTrue(
                    any(d in url for d in dominios[orgao]),
                    f"{orgao}: canal fora dos domínios oficiais ({url})")

    def test_doe_percent_encoding_ascii(self):
        """A URL de busca do DOU precisa ser ASCII (bug UnicodeEncodeError)."""
        for orgao in ("planalto", "mcti", "tse"):
            fonte = instanciar(orgao, logger=lambda *a, **k: None)
            for canal in fonte.canais:
                for _topico, url in canal.urls():
                    url.encode("ascii")  # levanta se houver acento cru

    def test_anpd_cobre_tipos_exigidos(self):
        """ANPD: notícias, resoluções/regulamentos, consultas, fiscalização e
        agenda regulatória precisam ter canal oficial."""
        fonte = instanciar("anpd", logger=lambda *a, **k: None)
        rotulos = " | ".join(c.rotulo for c in fonte.canais)
        for exigido in ("notícias", "regulação", "consultas", "fiscalização",
                        "agenda regulatória", "atos normativos"):
            self.assertIn(exigido, rotulos)

    def test_tse_usa_api_oficial_do_portal(self):
        fonte = instanciar("tse", logger=lambda *a, **k: None)
        urls = [c.url for c in fonte.canais]
        self.assertIn("https://www.tse.jus.br/++api++/@search", urls)

    def test_cnj_paginacao_por_page(self):
        fonte = instanciar("cnj", logger=lambda *a, **k: None)
        paginas = [c.opcoes.get("params", {}).get("page") for c in fonte.canais]
        self.assertIn(2, paginas)
        self.assertNotIn("offset", str(paginas))


if __name__ == "__main__":
    unittest.main(verbosity=2)
