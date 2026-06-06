"""
Package-level smoke tests: verify imports, CLI wiring, and key data shapes.
These do not make real HTTP requests.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import yaml


class TestPackageImports(unittest.TestCase):
    def test_download_module_importable(self):
        from cyberdrop.download import DownloadResult, download_album, download_all, extract_bunkr_cdn_url, extract_bunkr_filename

    def test_bookmarks_module_importable(self):
        from cyberdrop.bookmarks import Bookmarks, Creator, Link

    def test_tracking_module_importable(self):
        from cyberdrop.tracking import DownloadTracker, TRACKING_FILENAME

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


class TestBookmarks(unittest.TestCase):
    def test_load_normalizes_string_links(self):
        from cyberdrop.bookmarks import Bookmarks
        data = {"creators": [{"name": "Test", "links": ["https://example.com/a/1", "https://example.com/a/2"]}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as f:
            yaml.dump(data, f)
            tmp_path = f.name
        try:
            bm = Bookmarks.load(tmp_path)
            self.assertEqual(len(bm.creators), 1)
            self.assertEqual(bm.creators[0].name, "Test")
            links = bm.creators[0].links
            self.assertEqual(len(links), 2)
            self.assertEqual(links[0].url, "https://example.com/a/1")
            self.assertFalse(links[0].downloaded)
            self.assertEqual(links[0].name, "Link 1")
        finally:
            os.unlink(tmp_path)

    def test_load_preserves_existing_dict_links(self):
        from cyberdrop.bookmarks import Bookmarks
        data = {"creators": [{"name": "Test", "links": [{"name": "Pack 1", "url": "https://x.com/a/1", "downloaded": True}]}]}
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8") as f:
            yaml.dump(data, f)
            tmp_path = f.name
        try:
            bm = Bookmarks.load(tmp_path)
            lnk = bm.creators[0].links[0]
            self.assertEqual(lnk.name, "Pack 1")
            self.assertTrue(lnk.downloaded)
        finally:
            os.unlink(tmp_path)

    def test_round_trip(self):
        from cyberdrop.bookmarks import Bookmarks, Creator, Link
        bm = Bookmarks(creators=[
            Creator(
                name="TestCreator",
                links=[
                    Link(name="Pack 1", url="https://bunkr.cr/a/xxx", downloaded=True),
                    Link(name="Pack 2", url="https://cyberdrop.me/a/yyy"),
                ],
                consolidation_path="/path/to/dest",
            ),
        ])
        with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as f:
            tmp_path = f.name
        try:
            bm.save(tmp_path)
            bm2 = Bookmarks.load(tmp_path)
            c = bm2.creators[0]
            self.assertEqual(c.name, "TestCreator")
            self.assertEqual(c.consolidation_path, "/path/to/dest")
            self.assertEqual(c.links[0].name, "Pack 1")
            self.assertTrue(c.links[0].downloaded)
            self.assertEqual(c.links[1].url, "https://cyberdrop.me/a/yyy")
            self.assertFalse(c.links[1].downloaded)
        finally:
            os.unlink(tmp_path)

    def test_add_link_creates_creator_if_missing(self):
        from cyberdrop.bookmarks import Bookmarks
        bm = Bookmarks()
        lnk = bm.add_link("NewCreator", "https://bunkr.cr/a/test")
        self.assertEqual(len(bm.creators), 1)
        self.assertEqual(bm.creators[0].name, "NewCreator")
        self.assertEqual(lnk.url, "https://bunkr.cr/a/test")
        self.assertEqual(lnk.name, "NewCreator 1")

    def test_add_link_reuses_existing_creator(self):
        from cyberdrop.bookmarks import Bookmarks, Creator
        bm = Bookmarks(creators=[Creator(name="ExistingCreator")])
        bm.add_link("ExistingCreator", "https://bunkr.cr/a/test")
        self.assertEqual(len(bm.creators), 1)
        self.assertEqual(len(bm.creators[0].links), 1)

    def test_load_returns_empty_bookmarks_if_file_missing(self):
        from cyberdrop.bookmarks import Bookmarks
        bm = Bookmarks.load("/nonexistent/path/bookmarks.yml")
        self.assertEqual(bm.creators, [])

    def test_sanitize_filename(self):
        from cyberdrop.download import sanitize_filename
        self.assertEqual(sanitize_filename('file: "name"?.mp4'), "file- -name--.mp4")
        self.assertEqual(sanitize_filename(None), "")


class TestDownloadTracker(unittest.TestCase):
    def test_is_downloaded_false_when_no_file(self):
        from cyberdrop.tracking import DownloadTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = DownloadTracker(tmpdir)
            self.assertFalse(tracker.is_downloaded("https://example.com/file.mp4"))

    def test_mark_done_persists(self):
        from cyberdrop.tracking import DownloadTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = DownloadTracker(tmpdir)
            key = "https://example.com/file.mp4"
            self.assertFalse(tracker.is_downloaded(key))
            tracker.mark_done(key)
            self.assertTrue(tracker.is_downloaded(key))

    def test_new_tracker_same_dir_sees_marked_items(self):
        from cyberdrop.tracking import DownloadTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            DownloadTracker(tmpdir).mark_done("key1")
            tracker2 = DownloadTracker(tmpdir)
            self.assertTrue(tracker2.is_downloaded("key1"))
            self.assertFalse(tracker2.is_downloaded("key2"))

    def test_tracking_filename_constant(self):
        from cyberdrop.tracking import TRACKING_FILENAME
        self.assertEqual(TRACKING_FILENAME, "already_downloaded.txt")

    def test_injected_tracker_used_in_get_items_list(self):
        from cyberdrop.download import _get_items_list
        from cyberdrop.tracking import DownloadTracker

        bunkr_html = b"""
        <html>
          <head><title>Test Album | Bunkr</title></head>
          <body>
            <h1 class="truncate">Test Album</h1>
            <div class="theItem">
              <a class="after:absolute" href="https://bunkr.cr/f/abc123"></a>
              <p>file.mp4</p>
            </div>
          </body>
        </html>
        """
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.content = bunkr_html
        mock_resp.text = bunkr_html.decode()

        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = DownloadTracker(tmpdir)
            tracker.mark_done("https://bunkr.cr/f/abc123")

            with patch("cyberdrop.download._get_real_download_url") as mock_resolve, \
                 patch("cyberdrop.download._download_file") as mock_dl:
                mock_resolve.return_value = {
                    "url": "https://cdn.example.com/file.mp4", "size": -1,
                    "name": "file.mp4", "download_key": "https://bunkr.cr/f/abc123",
                }
                _get_items_list(mock_session, "https://bunkr.cr/a/xxx", None, False,
                                custom_path=tmpdir, tracker=tracker)
                mock_dl.assert_not_called()


class TestAlbumParsers(unittest.TestCase):
    def test_parse_bunkr_album_page_extracts_items(self):
        from bs4 import BeautifulSoup
        from cyberdrop.download import _parse_bunkr_album_page
        html = """
        <html>
          <head><title>Test Album | Bunkr</title></head>
          <body>
            <h1 class="truncate">Test Album</h1>
            <div class="theItem">
              <a class="after:absolute" href="https://bunkr.cr/f/abc123"></a>
              <p>file1.mp4</p>
            </div>
            <div class="theItem">
              <a class="after:absolute" href="https://bunkr.cr/f/def456"></a>
              <p>file2.jpg</p>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items, album_name, direct_link = _parse_bunkr_album_page(soup, "https://bunkr.cr/a/xxx")
        self.assertEqual(album_name, "Test Album")
        self.assertFalse(direct_link)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["url"], "https://bunkr.cr/f/abc123")
        self.assertEqual(items[0]["name"], "file1.mp4")
        self.assertEqual(items[1]["url"], "https://bunkr.cr/f/def456")

    def test_parse_bunkr_album_page_detects_direct_link(self):
        from bs4 import BeautifulSoup
        from cyberdrop.download import _parse_bunkr_album_page
        html = """
        <html>
          <head><title>Gallery | Bunkr</title></head>
          <body>
            <h1 class="truncate">Gallery</h1>
            <div class="lightgallery">
              <a href="/f/abc123" title="photo1.jpg">photo1.jpg</a>
              <a href="/f/def456" title="photo2.jpg">photo2.jpg</a>
            </div>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items, album_name, direct_link = _parse_bunkr_album_page(soup, "https://bunkr.cr/a/gallery")
        self.assertTrue(direct_link)
        self.assertEqual(len(items), 2)
        self.assertIn("bunkr.cr/f/abc123", items[0]["url"])

    def test_parse_cyberdrop_album_page_extracts_items(self):
        from bs4 import BeautifulSoup
        from cyberdrop.download import _parse_cyberdrop_album_page
        html = """
        <html>
          <body>
            <h1 id="title">My Cyberdrop Album</h1>
            <a class="image" href="/f/abc123">item1</a>
            <a class="image" href="/f/def456">item2</a>
          </body>
        </html>
        """
        soup = BeautifulSoup(html, "html.parser")
        items, album_name = _parse_cyberdrop_album_page(soup, "https://cyberdrop.me/a/xxx")
        self.assertEqual(album_name, "My Cyberdrop Album")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["url"], "https://cyberdrop.me/f/abc123")
        self.assertEqual(items[1]["url"], "https://cyberdrop.me/f/def456")

    def test_parse_cyberdrop_album_page_empty(self):
        from bs4 import BeautifulSoup
        from cyberdrop.download import _parse_cyberdrop_album_page
        html = '<html><body><h1 id="title">Empty Album</h1></body></html>'
        soup = BeautifulSoup(html, "html.parser")
        items, album_name = _parse_cyberdrop_album_page(soup, "https://cyberdrop.me/a/empty")
        self.assertEqual(album_name, "Empty Album")
        self.assertEqual(items, [])


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
