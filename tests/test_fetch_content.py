import unittest

import fetch_content as fc
from bs4 import BeautifulSoup


class TestFetchContent(unittest.TestCase):
    def test_extract_title_and_main_text(self):
        html = """
        <html>
          <head>
            <title>Ignored</title>
            <meta property="og:title" content="Real Title" />
            <meta name="author" content="Jane Doe" />
          </head>
          <body>
            <article>
              <p>This is a long paragraph about embedded systems debugging and firmware work.</p>
              <p>This is another long paragraph about driver design and tooling choices.</p>
              <p>This paragraph is intentionally long enough to be collected as content for export.</p>
              <p>This paragraph is also intentionally long enough to make article extraction win.</p>
              <p>This paragraph keeps the total extracted text comfortably above the threshold.</p>
              <p>This last paragraph ensures the sample article is treated like a meaningful page.</p>
            </article>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        self.assertEqual(fc.extract_title(soup), "Real Title")
        self.assertEqual(fc.extract_byline(soup), "Jane Doe")
        content = fc.extract_main_text(soup)
        self.assertIn("embedded systems debugging", content)


if __name__ == "__main__":
    unittest.main()
