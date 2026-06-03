import unittest

from dump import extract_bunkr_cdn_url, extract_bunkr_filename


class BunkrFilenameExtractionTests(unittest.TestCase):
    def test_extracts_filename_from_current_file_page_heading(self):
        html = """
        <html>
          <head>
            <title>My movie 6_23.mp4 | Bunkr</title>
            <meta property="og:title" content="My movie 6_23.mp4">
          </head>
          <body>
            <h1 class="text-subs font-semibold text-base sm:text-lg truncate">My movie 6_23.mp4</h1>
            <p style="display: none;">v-2.3.11</p>
          </body>
        </html>
        """

        self.assertEqual(extract_bunkr_filename(html), "My movie 6_23.mp4")

    def test_extracts_filename_from_legacy_the_item_block(self):
        html = """
        <html>
          <body>
            <div class="theItem" title="Legacy file.mp4">
              <p class="theName">Different text.mp4</p>
            </div>
          </body>
        </html>
        """

        self.assertEqual(extract_bunkr_filename(html), "Legacy file.mp4")

    def test_ignores_footer_version_when_no_filename_exists(self):
        html = """
        <html>
          <head><title>Bunkr</title></head>
          <body><footer><p style="display: none;">v-2.3.11</p></footer></body>
        </html>
        """

        self.assertIsNone(extract_bunkr_filename(html))

    def test_extracts_cdn_url_from_current_inline_script(self):
        html = r"""
        <html>
          <body>
            <script type="text/javascript">
              var jsCDN = "https:\/\/c5bu-b.cdn.cr\/storage\/media\/My-movie-6_23-L1cLsIGS.mp4";
              var signUrl = "https://glb-apisign.cdn.cr/sign";
            </script>
          </body>
        </html>
        """

        self.assertEqual(
            extract_bunkr_cdn_url(html),
            "https://c5bu-b.cdn.cr/storage/media/My-movie-6_23-L1cLsIGS.mp4",
        )


if __name__ == "__main__":
    unittest.main()
