import unittest

import run_pipeline as rp


class TestRunPipeline(unittest.TestCase):
    def test_query_expansion_depth_and_dedupe(self):
        queries = rp.generate_long_tail_queries("embedded systems", max_queries=70)
        self.assertGreaterEqual(len(queries), 60)
        self.assertEqual(len(queries), len(set(q.lower() for q in queries)))

    def test_normalize_url_drops_tracking(self):
        url = "https://example.com/path/?utm_source=x&utm_medium=y&id=7&feature=share"
        normalized = rp.normalize_url(url)
        self.assertIn("id=7", normalized)
        self.assertNotIn("utm_source", normalized)
        self.assertNotIn("utm_medium", normalized)
        self.assertNotIn("feature=share", normalized)

    def test_bucket_assignment(self):
        item = rp.Item(
            source="blogs",
            title="RTOS debugging guide for interrupt latency",
            url="https://example.com/a",
            snippet="step by step debug strategy",
            query="rtos debugging",
        )
        self.assertEqual(rp.assign_intent(item), "Debugging")

    def test_dedupe_collapses_similar_titles_and_urls(self):
        items = [
            rp.Item("youtube", "RTOS Debugging Guide", "https://x.com/a?utm_source=1", "", "q"),
            rp.Item("youtube", "RTOS debugging guide", "https://x.com/a", "", "q"),
            rp.Item("youtube", "RTOS Driver Implementation", "https://x.com/b", "", "q"),
        ]
        deduped = rp.dedupe_items(items, max_items=10)
        self.assertEqual(len(deduped), 2)

    def test_opportunistic_source_quality_gate(self):
        low_quora = [
            rp.Item("quora", "General question", "https://quora.com/q1", "", "q", score=1, intent="Career/Market"),
            rp.Item("quora", "Generic thread", "https://quora.com/q2", "", "q", score=2, intent="Career/Market"),
        ]
        # Need at least 3 items and avg >= 8 by policy.
        self.assertFalse(rp.source_quality_pass(low_quora))

    def test_host_key_normalizes_www(self):
        self.assertEqual(rp.host_key("https://www.example.com/a"), "example.com")


if __name__ == "__main__":
    unittest.main()
