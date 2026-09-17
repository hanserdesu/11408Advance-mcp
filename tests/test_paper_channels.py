# -*- coding: utf-8 -*-
"""出卷与交付通道测试：答案分离、页数预算、无打印机时的逐级退化。"""
import datetime
import os
import shutil
import unittest
from unittest import mock

from tests.util import PROJECT, demo_workspace, read, temp_workspace
from kaoyan_mcp import channels, paper

SPEC = {
    "title": "极限专项",
    "subject": "示例数学",
    "date": "2026-09-17",
    "instructions": "闭卷，写完整过程",
    "questions": [
        {"id": "Q1", "stem": "求极限：lim(x->0) (sin x)/x", "answer": "1",
         "atoms": ["SY-01-001"], "points": 10, "work_mm": 30},
        {"id": "Q2", "stem": "求极限：lim(x->0) (1-cos x)/x^2", "answer": "1/2",
         "atoms": ["SY-01-002"], "points": 10, "work_mm": 30},
    ],
}


class PaperTest(unittest.TestCase):
    def test_answers_never_leak_into_sheet(self):
        ws, tmp = temp_workspace()
        try:
            built = paper.write_sheet(ws, SPEC)
            html = read(built["html"])
            answer = read(built["answer"])
            self.assertIn("Q1", html)
            self.assertNotIn("答案", html)
            self.assertNotIn("1/2", html.split("Q2")[1].split("</section>")[0])
            self.assertIn("答案与讲评", answer)
            self.assertIn("1/2", answer)
            self.assertTrue(os.path.isfile(built["html"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_page_budget_splits_long_sheets(self):
        many = dict(SPEC)
        many["questions"] = [dict(q, id="Q%d" % i) for i, q in
                             enumerate([SPEC["questions"][0]] * 12, 1)]
        html, pages = paper.render_html(many)
        self.assertGreater(pages, 1)
        self.assertEqual(html.count('class="page"'), pages)

    def test_a5_holds_less_than_a4(self):
        spec = dict(SPEC)
        a4 = paper.estimate_pages(dict(spec, paper="A4"))
        a5 = paper.estimate_pages(dict(spec, paper="A5"))
        self.assertGreaterEqual(a5, a4)


class ChannelTest(unittest.TestCase):
    def test_probe_shape(self):
        ws = demo_workspace()
        info = channels.probe(ws)
        for key in ("os", "python", "browser", "printers", "channels", "order", "policy"):
            self.assertIn(key, info)
        self.assertTrue(info["channels"]["html"])
        self.assertTrue(info["channels"]["text"])

    def test_pdf_policy_falls_back_to_html_without_browser(self):
        ws, tmp = temp_workspace()
        try:
            built = paper.write_sheet(ws, SPEC)
            with mock.patch.object(channels, "find_browser", return_value=""):
                res = channels.deliver(ws, built, SPEC, policy=dict(policy="pdf"))
            self.assertTrue(res["ok"])
            self.assertEqual(res["channel"], "html")
            self.assertTrue(any("PDF" in w or "浏览器" in w for w in res["warnings"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_print_strict_never_silently_degrades(self):
        ws, tmp = temp_workspace()
        try:
            built = paper.write_sheet(ws, SPEC)
            with mock.patch.object(channels, "find_browser", return_value=""), \
                    mock.patch.object(channels, "list_printers", return_value=[]):
                res = channels.deliver(ws, built, SPEC, policy=dict(policy="print_strict"))
            self.assertFalse(res["ok"])
            self.assertIn("print_strict", " ".join(res["warnings"]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_text_channel_returns_sheet_inline(self):
        ws, tmp = temp_workspace()
        try:
            built = paper.write_sheet(ws, SPEC)
            res = channels.deliver(ws, built, SPEC, policy=dict(policy="text"))
            self.assertTrue(res["ok"])
            self.assertEqual(res["channel"], "text")
            self.assertIn("Q1", res["artifacts"]["text"])
            self.assertNotIn("答案", res["artifacts"]["text"])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def test_text_sheet_defaults_to_today(self):
        spec = dict(SPEC)
        spec.pop("date")
        text = channels.render_sheet_text(spec)
        self.assertIn(datetime.date.today().isoformat(), text)

    def test_pdf_render_works_on_this_machine_or_degrades_cleanly(self):
        ws, tmp = temp_workspace()
        try:
            built = paper.write_sheet(ws, SPEC)
            res = channels.deliver(ws, built, SPEC, policy=dict(policy="pdf"))
            if res["channel"] == "pdf":
                pdf = res["artifacts"]["pdf"]
                self.assertTrue(os.path.isfile(pdf))
                self.assertGreaterEqual(channels.count_pdf_pages(pdf), 1)
            else:
                self.assertEqual(res["channel"], "html")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()
