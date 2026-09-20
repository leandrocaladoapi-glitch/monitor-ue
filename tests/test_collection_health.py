import unittest
from datetime import datetime, timezone, timedelta
from scripts.check_collection import problems  # dataset timestampado em BRT (README)

class CollectionHealthTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.fromisoformat("2026-09-14T18:00:00-03:00")
        self.record = dict(fim="2026-09-14T16:24:35+00:00", status="concluida",
                           cobertura_pct=100, erros=[], procedimentos_pendentes=0)
    def test_zero_changes_is_success(self):
        self.record["mudancas_detectadas"] = 0
        self.assertEqual(problems(self.record, self.now), [])
    def test_success_status_does_not_hide_partial_coverage(self):
        self.record["cobertura_pct"] = 21.1
        self.assertTrue(problems(self.record, self.now))
        self.record["cobertura_pct"] = 100
        self.record["erros"] = ["HTTP timeout"]
        self.assertTrue(problems(self.record, self.now))
    def test_stale_and_invalid_dates(self):
        for date in ["2026-09-13T16:00:00-03:00", "invalid", "2026-09-15T12:00:00-03:00"]:
            self.record["fim"] = date
            self.assertTrue(problems(self.record, self.now))
    def test_date_uses_brasilia_not_utc(self):
        self.record["fim"] = "2026-09-15T01:00:00+00:00"
        self.assertEqual(problems(self.record, datetime.fromisoformat("2026-09-14T23:00:00-03:00")), [])
    def test_partial_and_pending_fail(self):
        self.record["status"] = "parcial"
        self.assertTrue(problems(self.record, self.now))
        self.record["status"] = "concluida"
        self.record["procedimentos_pendentes"] = 1
        self.assertTrue(problems(self.record, self.now))
        # Compat: registros antigos com a chave legada também detectam pendência
        del self.record["procedimentos_pendentes"]
        self.record["proposicoes_pendentes"] = 1
        self.assertTrue(problems(self.record, self.now))
