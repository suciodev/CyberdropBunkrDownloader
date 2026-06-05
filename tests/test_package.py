"""
Package-level smoke tests: verify imports, CLI wiring, and key data shapes.
These do not make real HTTP requests.
"""

import unittest
from unittest.mock import MagicMock, patch


class TestPackageImports(unittest.TestCase):
    def test_download_module_importable(self):
        from cyberdrop.download import DownloadResult, download_album, extract_bunkr_cdn_url, extract_bunkr_filename

    def test_bookmarks_io_importable(self):
        from cyberdrop.bookmarks_io import load_bookmarks, normalize_bookmarks, sanitize_filename, save_bookmarks

    def test_consolidate_importable(self):
        from cyberdrop.consolidate import consolidate_from_bookmarks, consolidate_creator_files

    def test_cli_parser_builds(self):
        from cyberdrop.cli import build_parser
        parser = build_parser()
        self.assertIsNotNone(parser)


class TestDownloadResult(unittest.TestCase):
    def test_success_result_shape(self):
        from cyberdrop.download import DownloadResult
        r = DownloadResult(success=True, folder_name="MyAlbum")
        self.assertTrue(r.success)
        self.assertEqual(r.folder_name, "MyAlbum")
        self.assertEqual(r.errors, [])

    def test_failure_result_shape(self):
        from cyberdrop.download import DownloadResult
        r = DownloadResult(success=False, errors=["HTTP 404"])
        self.assertFalse(r.success)
        self.assertIsNone(r.folder_name)
        self.assertIn("HTTP 404", r.errors)

    def test_download_album_returns_failure_on_http_error(self):
        from cyberdrop.download import download_album

        mock_response = MagicMock()
        mock_response.status_code = 404

        with patch("cyberdrop.download.create_session") as mock_session_fn:
            mock_session = MagicMock()
            mock_session.get.return_value = mock_response
            mock_session_fn.return_value = mock_session

            result = download_album("https://bunkr.cr/a/TESTFAIL")

        self.assertFalse(result.success)
        self.assertTrue(len(result.errors) > 0)


class TestBookmarksIO(unittest.TestCase):
    def test_normalize_string_links(self):
        from cyberdrop.bookmarks_io import normalize_bookmarks
        bm = {"creators": [{"name": "Test", "links": ["https://example.com/a/1", "https://example.com/a/2"]}]}
        out = normalize_bookmarks(bm)
        links = out["creators"][0]["links"]
        self.assertEqual(len(links), 2)
        self.assertEqual(links[0]["url"], "https://example.com/a/1")
        self.assertFalse(links[0]["downloaded"])
        self.assertEqual(links[0]["name"], "Link 1")

    def test_normalize_preserves_existing_dicts(self):
        from cyberdrop.bookmarks_io import normalize_bookmarks
        bm = {"creators": [{"name": "Test", "links": [{"name": "Pack 1", "url": "https://x.com/a/1", "downloaded": True}]}]}
        out = normalize_bookmarks(bm)
        link = out["creators"][0]["links"][0]
        self.assertEqual(link["name"], "Pack 1")
        self.assertTrue(link["downloaded"])

    def test_sanitize_filename(self):
        from cyberdrop.bookmarks_io import sanitize_filename
        self.assertEqual(sanitize_filename('file: "name"?.mp4'), "file- -name--.mp4")
        self.assertEqual(sanitize_filename(None), "")


class TestCliSubcommands(unittest.TestCase):
    def test_download_subcommand_parses(self):
        from cyberdrop.cli import build_parser
        p = build_parser()
        args = p.parse_args(["download", "-u", "https://bunkr.cr/a/TEST"])
        self.assertEqual(args.command, "download")
        self.assertEqual(args.url, "https://bunkr.cr/a/TEST")

    def test_bookmarks_subcommand_parses(self):
        from cyberdrop.cli import build_parser
        p = build_parser()
        args = p.parse_args(["bookmarks", "-c", "Alice", "Bob", "--skip-downloaded"])
        self.assertEqual(args.command, "bookmarks")
        self.assertEqual(args.creator, ["Alice", "Bob"])
        self.assertTrue(args.skip_downloaded)
        self.assertFalse(hasattr(args, "timeout"))

    def test_import_subcommand_parses(self):
        from cyberdrop.cli import build_parser
        p = build_parser()
        args = p.parse_args(["import", "-c", "CreatorName"])
        self.assertEqual(args.command, "import")
        self.assertEqual(args.creator, "CreatorName")

    def test_consolidate_subcommand_parses(self):
        from cyberdrop.cli import build_parser
        p = build_parser()
        args = p.parse_args(["consolidate", "-o", "my_downloads"])
        self.assertEqual(args.command, "consolidate")
        self.assertEqual(args.output, "my_downloads")


if __name__ == "__main__":
    unittest.main()
