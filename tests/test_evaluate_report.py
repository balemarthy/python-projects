import tempfile
import unittest
from pathlib import Path

import evaluate_report as er


class TestEvaluateReport(unittest.TestCase):
    def test_parse_and_score(self):
        content = """# Research Report - 2026-04-27

## embedded systems

Coverage: **GOOD** (14 links across 3 sources)

### Debugging

- [A](https://a.com) (youtube) - x

### Implementation

- [B](https://b.com) (blogs) - y

### Tooling

- [C](https://c.com) (medium) - z

### Interview

- [D](https://d.com) (reddit)

### Projects

- [E](https://e.com) (youtube)

### Career/Market

- [F](https://f.com) (quora)
"""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "latest_news_2026-04-27.md"
            p.write_text(content, encoding="utf-8")
            result = er.evaluate(p)
            self.assertGreater(result["overall"], 50)
            self.assertIn("embedded systems", result["themes"])


if __name__ == "__main__":
    unittest.main()
