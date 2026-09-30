#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes da camada de inteligência regulatória (Módulos 1–18 do produto).

Cobrem: integridade do dataset gerado, URL oficial obrigatória, deduplicação,
prazos, rúbrica de prioridade, motor de impacto, geração de páginas, links,
sitemap e a regra de que nenhuma análise aparece sem fonte oficial.
"""
import json
import re
import sys
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from regulatory import product, taxonomy as tx  # noqa: E402
from regulatory.engine import (build_events, official_source,  # noqa: E402
                               reference_date)

DOCS = ROOT / "docs"
SITE = "https://monitor-ue.vercel.app"
EVENT_KEYS = ["regulatory_event", "summary", "affected_sectors", "affected_company_types",
              "affected_functions", "obligations", "deadlines", "risks", "opportunities",
              "recommended_actions", "impact_level", "priority", "confidence", "official_sources"]


class TaxonomyTests(unittest.TestCase):
    def test_24_sectors_and_known_slugs(self):
        self.assertEqual(len(tx.SECTORS), 24)
        for slug in ("bancos", "fintech", "seguros", "saude", "pharma", "saas", "cloud",
                     "provedores-de-ia", "modelos-de-fundacao", "telecom", "ecommerce",
                     "marketplaces", "adtech", "martech", "automotivo", "manufatura", "energia",
                     "utilities", "hr-tech", "recrutamento", "educacao", "legaltech",
                     "ciberseguranca", "data-centers"):
            self.assertIn(slug, tx.SECTORS)

    def test_every_theme_and_sector_function_resolves(self):
        keys = tx.all_theme_function_keys() | tx.all_sector_function_keys()
        unresolved = [key for key in keys if not tx.normalize_function(key)]
        self.assertEqual(unresolved, [], f"funções não normalizadas: {unresolved}")

    def test_priorities_and_confidence_scale(self):
        self.assertEqual(tx.CONFIDENCE["confirmed"], 0.95)
        self.assertEqual(tx.CONFIDENCE_FLOOR, 0.60)
        self.assertEqual(set(tx.PRIORITIES), {"urgent", "high", "medium", "monitor"})
        self.assertEqual(set(tx.IMPACT_LEVELS), {"critical", "high", "medium", "low"})


class ImpactEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = build_events()
        cls.published = cls.result["published"]

    def test_every_published_event_has_official_source(self):
        for event in self.published:
            self.assertTrue(event["official_sources"], event["id"])
            for url in event["official_sources"]:
                self.assertTrue(official_source(url), f"{event['id']} → {url}")

    def test_no_event_without_confidence_floor_is_published(self):
        for event in self.published:
            self.assertGreaterEqual(event["confidence"], tx.CONFIDENCE_FLOOR, event["id"])
        for excluded in self.result["excluded"]:
            self.assertLess(excluded["confidence"], tx.CONFIDENCE_FLOOR)

    def test_required_schema_keys_present(self):
        for event in self.published:
            for key in EVENT_KEYS:
                self.assertIn(key, event, f"{event['id']} sem '{key}'")
            for layer in ("fact", "analysis", "interpretation", "recommendations", "so_what"):
                self.assertIn(layer, event, f"{event['id']} sem camada '{layer}'")

    def test_no_duplicate_ids_or_sources(self):
        ids = [event["id"] for event in self.published]
        self.assertEqual(len(ids), len(set(ids)))
        keys = [(event["fact"]["source_url"], event["regulatory_event"]) for event in self.published]
        self.assertEqual(len(keys), len(set(keys)))

    def test_deadlines_have_iso_date_and_source(self):
        found = 0
        for event in self.published:
            for deadline in event.get("deadlines_full") or []:
                found += 1
                self.assertRegex(deadline["date"], r"^\d{4}-\d{2}-\d{2}$")
                self.assertTrue(official_source(deadline["source_url"]))
                self.assertIsInstance(deadline["days_remaining"], int)
        self.assertGreater(found, 0, "nenhum prazo extraído do dataset")

    def test_ai_act_and_digital_omnibus_milestones(self):
        norms = [event for event in self.published if event["source_kind"] == "norma"]
        self.assertGreaterEqual(len(norms), 2)
        all_dates = {d["date"] for event in norms for d in event["deadlines_full"]}
        for expected in ("2024-08-01", "2025-02-02", "2025-08-02", "2026-08-02", "2027-12-02", "2028-08-02",
                         "2026-07-27", "2026-12-02"):
            self.assertIn(expected, all_dates, f"marco ausente: {expected}")

    def test_priority_rubric_is_deterministic(self):
        first = build_events()["published"]
        second = build_events()["published"]
        self.assertEqual([(e["id"], e["impact_score"], e["priority"]) for e in first],
                         [(e["id"], e["impact_score"], e["priority"]) for e in second])

    def test_priority_matches_impact_level_bands(self):
        for event in self.published:
            score = event["impact_score"]
            if score >= 85:
                self.assertEqual(event["priority"], "urgent")
                self.assertEqual(event["impact_level"], "critical")
            elif score >= 70:
                self.assertEqual(event["priority"], "high")
            elif score >= 50:
                self.assertEqual(event["priority"], "medium")
            else:
                self.assertEqual(event["priority"], "monitor")

    def test_so_what_block_is_filled(self):
        for event in self.published:
            so = event["so_what"]
            for key in ("consequence", "functions", "possible_costs", "adaptation_needed",
                        "risk_of_inaction", "next_step"):
                self.assertTrue(so.get(key), f"{event['id']} sem so_what.{key}")

    def test_reference_date_comes_from_dataset(self):
        self.assertRegex(reference_date({"updates": {"meta": {"execucao": "2026-09-29"}}}).isoformat(),
                         r"^\d{4}-\d{2}-\d{2}$")

    def test_neutral_company_language(self):
        text = " ".join(event["interpretation"]["text"] for event in self.published).lower()
        self.assertIn("potencialmente afetada", text)
        self.assertNotIn("está enquadrada", text)


class ProductLayerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = product.build_all()

    def test_all_files_present(self):
        for name in ("events", "deadlines", "enforcement", "sectors", "alerts", "briefing",
                     "companies", "watchlist", "manifest"):
            self.assertIn(name, self.data)

    def test_deadlines_windows_are_consistent(self):
        deadlines = self.data["deadlines"]
        index = {m["id"]: m for m in deadlines["milestones"]}
        for window, ids in deadlines["windows"].items():
            limit = {"d30": 30, "d90": 90, "d180": 180, "d365": 365}[window]
            for mid in ids:
                self.assertIn(mid, index)
                self.assertTrue(0 <= index[mid]["days_remaining"] <= limit)

    def test_every_sector_has_required_blocks(self):
        sectors = self.data["sectors"]["sectors"]
        self.assertEqual(len(sectors), 24)
        for sector in sectors:
            for key in ("recent_changes", "obligations", "risks", "recommended_actions",
                        "deadlines", "related_acts"):
                self.assertIn(key, sector)

    def test_alerts_follow_executive_template(self):
        alerts = self.data["alerts"]["alerts"]
        self.assertTrue(alerts)
        for alert in alerts:
            for marker in ("Evento:", "Impacto:", "Afeta:", "Áreas internas:", "O que mudou:",
                           "Ação recomendada:", "Prazo:", "Fonte oficial:"):
                self.assertIn(marker, alert["text"])

    def test_briefing_has_eight_sections(self):
        for key in ("daily", "weekly"):
            sections = self.data["briefing"][key]["sections"]
            self.assertEqual(len(sections), 8)
            self.assertTrue(all("empty_message" in section for section in sections))

    def test_company_profiles_are_hedged_and_evidence_aware(self):
        for profile in self.data["companies"]["companies"]:
            self.assertIn("potencialmente afetada", profile["hedge"])
            self.assertIn("avaliação jurídica específica", profile["hedge"])
            self.assertIn(profile["evidence_status"],
                          ("menção em fonte oficial do dataset", "sem menção direta no dataset atual"))
            for item in profile["related_acts"]:
                self.assertTrue(item["source_url"].startswith("https://"))

    def test_manifest_enforces_product_rules(self):
        manifest = self.data["manifest"]
        self.assertEqual(manifest["events_without_official_source"], 0)
        self.assertGreaterEqual(manifest["confidence_min"], tx.CONFIDENCE_FLOOR)
        self.assertEqual(manifest["events_published"] + manifest["events_excluded_low_confidence"],
                         manifest["events_total"])

    def test_enforcement_structure(self):
        for case in self.data["enforcement"]["cases"]:
            for key in ("event", "authority", "legal_basis", "decision", "consequence", "regulatory_lesson"):
                self.assertTrue(case.get(key), f"{case['id']} sem '{key}'")
            self.assertTrue(official_source(case["source_url"]))


@unittest.skipUnless((DOCS / "prazos" / "index.html").exists(), "site não construído (rode scripts/build_site.py)")
class PublishedPagesTests(unittest.TestCase):
    def test_module_pages_exist(self):
        for rel in ("impacto/index.html", "setores/index.html", "prazos/index.html", "enforcement/index.html",
                    "empresas/index.html", "jurisprudencia/index.html", "diff/index.html",
                    "alertas-executivos/index.html", "briefing-executivo/index.html", "demo/index.html",
                    "produto/index.html", "como-analisamos/index.html"):
            self.assertTrue((DOCS / rel).exists(), rel)

    def test_lead_generation_pages_exist(self):
        for slug in ("eu-ai-act-deadlines", "gpai-compliance", "ai-act-banking", "ai-act-healthcare",
                     "ai-act-saas", "ai-act-foundation-models", "ai-office-updates", "edpb-ai-guidelines"):
            self.assertTrue((DOCS / slug / "index.html").exists(), slug)

    def test_public_pages_are_indexable(self):
        for path in DOCS.rglob("index.html"):
            relative = path.relative_to(DOCS).as_posix()
            if relative in ("app/index.html", "login/index.html"):
                continue
            html = path.read_text(encoding="utf-8")
            if "iq-" in html:  # páginas da camada de inteligência
                self.assertNotIn('content="noindex', html, relative)

    def test_internal_links_resolve(self):
        pattern = re.compile(r'href="(/(?:[^"#]*))"')
        for folder in ("impacto", "prazos", "setores", "demo", "empresas"):
            for path in (DOCS / folder).rglob("index.html"):
                html = path.read_text(encoding="utf-8")
                for href in set(pattern.findall(html)):
                    if href.startswith("//"):
                        continue
                    href = href.split("?")[0].split("#")[0]
                    if not href:
                        continue
                    target = DOCS / href.lstrip("/")
                    if href.endswith("/") or href == "":
                        target = target / "index.html"
                    self.assertTrue(target.exists(), f"{path.relative_to(DOCS)} → {href}")

    def test_sitemap_includes_product_urls(self):
        root = ET.fromstring((DOCS / "sitemap.xml").read_text(encoding="utf-8"))
        urls = {node.text for node in root.findall(
            "{http://www.sitemaps.org/schemas/sitemap/0.9}url/{http://www.sitemaps.org/schemas/sitemap/0.9}loc")}
        for path in ("prazos/", "impacto/", "setores/", "enforcement/", "empresas/", "demo/", "produto/"):
            self.assertIn(f"{SITE}/{path}", urls, path)

    def test_home_has_executive_dashboard(self):
        html = (DOCS / "index.html").read_text(encoding="utf-8")
        self.assertIn("painel-executivo", html)
        self.assertIn("mudanças regulatórias exigem atenção", html)
        for marker in ("Mudanças críticas", "Prazos", "Alertas de alto impacto", "Enforcement",
                       "Consultas abertas"):
            self.assertIn(marker, html)


class CommercialConsolidationTests(unittest.TestCase):
    """Módulos 12, 14 e 17: watchlists prontas, planos conceituais e fim dos resquícios legados."""

    def test_watchlist_page_lists_presets(self):
        html = (DOCS / "watchlist" / "index.html").read_text(encoding="utf-8")
        for marker in ("Watchlists prontas", "Por empresa", "Por tema", "Por setor",
                       "Por regulador", "Por tipo de ato"):
            self.assertIn(marker, html)

    def test_watchlist_presets_come_from_dataset(self):
        data = json.loads((ROOT / "data" / "intelligence" / "watchlist.json").read_text(encoding="utf-8"))
        self.assertTrue(data["presets"])
        html = (DOCS / "watchlist" / "index.html").read_text(encoding="utf-8")
        for preset in data["presets"]:
            self.assertIn(preset["name"], html)

    def test_product_page_presents_conceptual_plans(self):
        html = (DOCS / "produto" / "index.html").read_text(encoding="utf-8")
        for plan in ("FREE", "PRO", "BUSINESS", "ENTERPRISE"):
            self.assertIn(plan, html)
        self.assertIn("Sem pagamento online nesta fase", html)

    def test_commercial_pages_link_to_plan_ladder_without_currency(self):
        for rel in ("solucoes/index.html", "diagnostico/index.html", "para-empresas/index.html"):
            html = (DOCS / rel).read_text(encoding="utf-8")
            self.assertNotIn("R$", html, rel)

    def test_no_legacy_monitor_markers_in_published_html(self):
        forbidden = ("R$", "camara.leg.br", "senado.leg.br", "anpd.gov.br", "Câmara dos Deputados")
        for path in DOCS.rglob("*.html"):
            relative = path.relative_to(DOCS).as_posix()
            html = path.read_text(encoding="utf-8")
            for marker in forbidden:
                self.assertNotIn(marker, html, f"{relative}: {marker}")

    def test_legacy_sector_pages_point_to_impact_matrix(self):
        known = {s["slug"] for s in json.loads(
            (ROOT / "data" / "intelligence" / "sectors.json").read_text(encoding="utf-8"))["sectors"]}
        legacy = [d for d in (DOCS / "setores").iterdir() if d.is_dir() and d.name not in known]
        self.assertTrue(legacy, "esperava páginas setoriais legadas para consolidar")
        for directory in legacy:
            html = (directory / "index.html").read_text(encoding="utf-8")
            self.assertIn("Matriz de impacto regulatório", html, directory.name)


if __name__ == "__main__":
    unittest.main()
