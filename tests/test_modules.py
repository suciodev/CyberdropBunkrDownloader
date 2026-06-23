"""
Tests for consolidate, bookmarks_cmd, and importer modules.
No real HTTP requests are made.
"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml


# ---------------------------------------------------------------------------
# consolidate
# ---------------------------------------------------------------------------

class TestNormalizeName(unittest.TestCase):
    def test_strips_non_alphanumeric(self):
        from cyberdrop.consolidate import _normalize_name
        self.assertEqual(_normalize_name("Hello World!"), "helloworld")

    def test_lowercases(self):
        from cyberdrop.consolidate import _normalize_name
        self.assertEqual(_normalize_name("UPPER"), "upper")

    def test_empty_string(self):
        from cyberdrop.consolidate import _normalize_name
        self.assertEqual(_normalize_name(""), "")


class TestFolderMatchesCreator(unittest.TestCase):
    def test_exact_match(self):
        from cyberdrop.consolidate import _folder_matches_creator
        self.assertTrue(_folder_matches_creator("alice", "alice"))

    def test_case_insensitive_match(self):
        from cyberdrop.consolidate import _folder_matches_creator
        self.assertTrue(_folder_matches_creator("Alice123", "alice"))

    def test_multi_word_creator_all_parts_present(self):
        from cyberdrop.consolidate import _folder_matches_creator
        self.assertTrue(_folder_matches_creator("johndoe2024", "John Doe"))

    def test_no_match(self):
        from cyberdrop.consolidate import _folder_matches_creator
        self.assertFalse(_folder_matches_creator("someotherfolder", "Alice"))

    def test_partial_match_not_enough(self):
        from cyberdrop.consolidate import _folder_matches_creator
        # "alice" matches "alice" in the folder but "smith" does not
        self.assertFalse(_folder_matches_creator("alice", "Alice Smith"))


class TestUniqueFilename(unittest.TestCase):
    def test_no_conflict(self):
        from cyberdrop.consolidate import _unique_filename
        with tempfile.TemporaryDirectory() as tmpdir:
            result = _unique_filename(Path(tmpdir), "photo.jpg")
            self.assertEqual(result, "photo.jpg")

    def test_conflict_appends_counter(self):
        from cyberdrop.consolidate import _unique_filename
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "photo.jpg").touch()
            result = _unique_filename(Path(tmpdir), "photo.jpg")
            self.assertEqual(result, "photo_1.jpg")

    def test_multiple_conflicts(self):
        from cyberdrop.consolidate import _unique_filename
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "photo.jpg").touch()
            Path(tmpdir, "photo_1.jpg").touch()
            result = _unique_filename(Path(tmpdir), "photo.jpg")
            self.assertEqual(result, "photo_2.jpg")

    def test_no_extension(self):
        from cyberdrop.consolidate import _unique_filename
        with tempfile.TemporaryDirectory() as tmpdir:
            Path(tmpdir, "README").touch()
            result = _unique_filename(Path(tmpdir), "README")
            self.assertEqual(result, "README_1")


class TestMoveFiles(unittest.TestCase):
    def test_moves_files_to_target(self):
        from cyberdrop.consolidate import _move_files
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            Path(src, "file1.jpg").write_text("a")
            Path(src, "file2.mp4").write_text("b")
            moved, dupes, skipped, errors = _move_files(Path(src), Path(dst))
            self.assertEqual(moved, 2)
            self.assertEqual(dupes, 0)
            self.assertEqual(errors, [])
            self.assertTrue(Path(dst, "file1.jpg").exists())
            self.assertTrue(Path(dst, "file2.mp4").exists())

    def test_skips_already_downloaded_txt(self):
        from cyberdrop.consolidate import _move_files
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            Path(src, "already_downloaded.txt").write_text("x")
            Path(src, "real.jpg").write_text("y")
            moved, dupes, skipped, errors = _move_files(Path(src), Path(dst))
            self.assertEqual(moved, 1)
            self.assertIn("already_downloaded.txt", skipped)
            self.assertFalse(Path(dst, "already_downloaded.txt").exists())

    def test_skips_subdirectories(self):
        from cyberdrop.consolidate import _move_files
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            Path(src, "subdir").mkdir()
            moved, dupes, skipped, errors = _move_files(Path(src), Path(dst))
            self.assertEqual(moved, 0)
            self.assertIn("subdir", skipped)

    def test_renames_duplicate(self):
        from cyberdrop.consolidate import _move_files
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            Path(src, "photo.jpg").write_text("new")
            Path(dst, "photo.jpg").write_text("existing")
            moved, dupes, skipped, errors = _move_files(Path(src), Path(dst))
            self.assertEqual(moved, 1)
            self.assertEqual(dupes, 1)
            self.assertTrue(Path(dst, "photo_1.jpg").exists())


class TestConsolidateCreatorFiles(unittest.TestCase):
    def test_missing_source_dir_returns_error(self):
        from cyberdrop.consolidate import consolidate_creator_files
        result = consolidate_creator_files("Alice", [], "/nonexistent/path", "/tmp/dest")
        self.assertFalse(result["success"])
        self.assertTrue(len(result["errors"]) > 0)

    def test_moves_files_from_named_album(self):
        from cyberdrop.consolidate import consolidate_creator_files
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as dest:
            album_dir = Path(base, "MyAlbum")
            album_dir.mkdir()
            (album_dir / "photo.jpg").write_text("x")
            result = consolidate_creator_files("Alice", ["MyAlbum"], base, dest)
            self.assertTrue(result["success"])
            self.assertEqual(result["files_moved"], 1)
            self.assertTrue(Path(dest, "photo.jpg").exists())

    def test_fuzzy_matches_creator_folder(self):
        from cyberdrop.consolidate import consolidate_creator_files
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as dest:
            folder = Path(base, "alicejones2024")
            folder.mkdir()
            (folder / "clip.mp4").write_text("x")
            result = consolidate_creator_files("Alice Jones", [], base, dest)
            self.assertTrue(result["success"])
            self.assertEqual(result["files_moved"], 1)

    def test_empty_album_list_no_match_moves_nothing(self):
        from cyberdrop.consolidate import consolidate_creator_files
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as dest:
            unrelated = Path(base, "unrelated")
            unrelated.mkdir()
            (unrelated / "file.jpg").write_text("x")
            result = consolidate_creator_files("Alice", [], base, dest)
            self.assertEqual(result["files_moved"], 0)


class TestConsolidateFromBookmarks(unittest.TestCase):
    def test_skips_creators_without_consolidation_path(self):
        from cyberdrop.bookmarks import Bookmarks, Creator, Link
        from cyberdrop.consolidate import consolidate_from_bookmarks
        bm = Bookmarks(creators=[Creator(name="NoCon", links=[Link(name="L1", url="https://x.com/a/1")])])
        with tempfile.TemporaryDirectory() as base:
            result = consolidate_from_bookmarks(bm, base)
        self.assertEqual(result["total_creators"], 1)
        self.assertEqual(len(result["consolidations"]), 0)

    def test_consolidates_creator_with_path(self):
        from cyberdrop.bookmarks import Bookmarks, Creator, Link
        from cyberdrop.consolidate import consolidate_from_bookmarks
        with tempfile.TemporaryDirectory() as base, tempfile.TemporaryDirectory() as dest:
            album_dir = Path(base, "Pack1")
            album_dir.mkdir()
            (album_dir / "file.jpg").write_text("x")
            bm = Bookmarks(creators=[Creator(
                name="Alice",
                links=[Link(name="Pack1", url="https://x.com/a/1")],
                consolidation_path=dest,
            )])
            result = consolidate_from_bookmarks(bm, base)
        self.assertIn("Alice", result["consolidations"])
        self.assertTrue(result["consolidations"]["Alice"]["success"])


# ---------------------------------------------------------------------------
# importer
# ---------------------------------------------------------------------------

class TestValidateUrl(unittest.TestCase):
    def test_valid_https(self):
        from cyberdrop.importer import validate_url
        self.assertTrue(validate_url("https://bunkr.cr/a/abc123"))

    def test_valid_http(self):
        from cyberdrop.importer import validate_url
        self.assertTrue(validate_url("http://cyberdrop.me/a/test"))

    def test_missing_scheme(self):
        from cyberdrop.importer import validate_url
        self.assertFalse(validate_url("bunkr.cr/a/abc123"))

    def test_empty_string(self):
        from cyberdrop.importer import validate_url
        self.assertFalse(validate_url(""))

    def test_ftp_scheme_rejected(self):
        from cyberdrop.importer import validate_url
        self.assertFalse(validate_url("ftp://example.com/file.zip"))

    def test_whitespace_trimmed(self):
        from cyberdrop.importer import validate_url
        self.assertTrue(validate_url("  https://bunkr.cr/a/abc  "))


class TestRunImport(unittest.TestCase):
    def _make_bookmarks_file(self, tmpdir: str, data: dict) -> str:
        path = os.path.join(tmpdir, "bookmarks.yml")
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        return path

    def test_imports_new_urls(self):
        from cyberdrop.importer import run_import
        with tempfile.TemporaryDirectory() as tmpdir:
            bm_path = self._make_bookmarks_file(tmpdir, {"creators": []})
            stdin = io.StringIO("https://bunkr.cr/a/abc\nhttps://bunkr.cr/a/def\n")
            with patch("sys.stdin", stdin):
                run_import("Alice", bm_path)
            with open(bm_path, encoding="utf-8") as f:
                saved = yaml.safe_load(f)
            urls = [lnk["url"] for lnk in saved["creators"][0]["links"]]
            self.assertIn("https://bunkr.cr/a/abc", urls)
            self.assertIn("https://bunkr.cr/a/def", urls)

    def test_skips_duplicate_urls(self):
        from cyberdrop.importer import run_import
        with tempfile.TemporaryDirectory() as tmpdir:
            existing_url = "https://bunkr.cr/a/existing"
            bm_path = self._make_bookmarks_file(tmpdir, {
                "creators": [{"name": "Alice", "links": [{"name": "L1", "url": existing_url, "downloaded": False}]}]
            })
            stdin = io.StringIO(f"{existing_url}\nhttps://bunkr.cr/a/new\n")
            with patch("sys.stdin", stdin):
                run_import("Alice", bm_path)
            with open(bm_path, encoding="utf-8") as f:
                saved = yaml.safe_load(f)
            alice = next(c for c in saved["creators"] if c["name"] == "Alice")
            urls = [lnk["url"] for lnk in alice["links"]]
            self.assertEqual(urls.count(existing_url), 1)
            self.assertIn("https://bunkr.cr/a/new", urls)

    def test_skips_invalid_urls(self):
        from cyberdrop.importer import run_import
        with tempfile.TemporaryDirectory() as tmpdir:
            bm_path = self._make_bookmarks_file(tmpdir, {"creators": []})
            stdin = io.StringIO("not-a-url\nhttps://bunkr.cr/a/valid\n")
            with patch("sys.stdin", stdin):
                run_import("Alice", bm_path)
            with open(bm_path, encoding="utf-8") as f:
                saved = yaml.safe_load(f)
            urls = [lnk["url"] for lnk in saved["creators"][0]["links"]]
            self.assertEqual(len(urls), 1)
            self.assertEqual(urls[0], "https://bunkr.cr/a/valid")

    def test_does_not_save_if_nothing_imported(self):
        from cyberdrop.importer import run_import
        with tempfile.TemporaryDirectory() as tmpdir:
            bm_path = self._make_bookmarks_file(tmpdir, {"creators": []})
            mtime_before = os.path.getmtime(bm_path)
            stdin = io.StringIO("not-a-url\n")
            with patch("sys.stdin", stdin):
                run_import("Alice", bm_path)
            self.assertAlmostEqual(os.path.getmtime(bm_path), mtime_before, places=1)


# ---------------------------------------------------------------------------
# bookmarks_cmd
# ---------------------------------------------------------------------------

class TestIsAlreadyDownloaded(unittest.TestCase):
    def test_false_when_downloads_dir_missing(self):
        from cyberdrop.bookmarks_cmd import is_already_downloaded
        self.assertFalse(is_already_downloaded("https://x.com/a/1", "/nonexistent/downloads"))

    def test_true_when_tracker_has_url(self):
        from cyberdrop.bookmarks_cmd import is_already_downloaded
        from cyberdrop.tracking import DownloadTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            DownloadTracker(tmpdir).mark_done("https://bunkr.cr/a/abc")
            self.assertTrue(is_already_downloaded("https://bunkr.cr/a/abc", tmpdir))

    def test_false_when_url_not_tracked(self):
        from cyberdrop.bookmarks_cmd import is_already_downloaded
        from cyberdrop.tracking import DownloadTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            DownloadTracker(tmpdir).mark_done("https://bunkr.cr/a/other")
            self.assertFalse(is_already_downloaded("https://bunkr.cr/a/abc", tmpdir))

    def test_true_when_tracker_in_subdirectory(self):
        from cyberdrop.bookmarks_cmd import is_already_downloaded
        from cyberdrop.tracking import DownloadTracker
        with tempfile.TemporaryDirectory() as tmpdir:
            subdir = Path(tmpdir, "MyAlbum")
            subdir.mkdir()
            DownloadTracker(subdir).mark_done("https://bunkr.cr/a/abc")
            self.assertTrue(is_already_downloaded("https://bunkr.cr/a/abc", tmpdir))


class TestRunBookmarks(unittest.TestCase):
    def _make_bookmarks_file(self, tmpdir: str, creators: list) -> str:
        path = os.path.join(tmpdir, "bookmarks.yml")
        data = {"creators": creators}
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        return path

    def test_exits_when_bookmarks_missing(self):
        from cyberdrop.bookmarks_cmd import run_bookmarks
        with self.assertRaises(SystemExit):
            run_bookmarks(bookmarks_path="/nonexistent/bookmarks.yml")

    def test_downloads_undownloaded_links(self):
        from cyberdrop.bookmarks_cmd import run_bookmarks
        with tempfile.TemporaryDirectory() as tmpdir:
            bm_path = self._make_bookmarks_file(tmpdir, [{
                "name": "Alice",
                "links": [{"name": "Pack1", "url": "https://bunkr.cr/a/abc", "downloaded": False}],
            }])
            mock_result = MagicMock()
            mock_result.success = True
            mock_result.folder_name = "Pack1"
            mock_result.errors = []
            with patch("cyberdrop.bookmarks_cmd.download_album", return_value=mock_result) as mock_dl:
                run_bookmarks(bookmarks_path=bm_path, output_dir=tmpdir, no_update=True)
            mock_dl.assert_called_once_with(
                "https://bunkr.cr/a/abc", extensions=None, output_dir=tmpdir
            )

    def test_skips_already_downloaded_links_with_flag(self):
        from cyberdrop.bookmarks_cmd import run_bookmarks
        with tempfile.TemporaryDirectory() as tmpdir:
            bm_path = self._make_bookmarks_file(tmpdir, [{
                "name": "Alice",
                "links": [{"name": "Pack1", "url": "https://bunkr.cr/a/abc", "downloaded": True}],
            }])
            with patch("cyberdrop.bookmarks_cmd.download_album") as mock_dl:
                run_bookmarks(bookmarks_path=bm_path, output_dir=tmpdir, skip_downloaded=True, no_update=True)
            mock_dl.assert_not_called()

    def test_creator_filter_skips_other_creators(self):
        from cyberdrop.bookmarks_cmd import run_bookmarks
        with tempfile.TemporaryDirectory() as tmpdir:
            bm_path = self._make_bookmarks_file(tmpdir, [
                {"name": "Alice", "links": [{"name": "P1", "url": "https://bunkr.cr/a/alice", "downloaded": False}]},
                {"name": "Bob",   "links": [{"name": "P2", "url": "https://bunkr.cr/a/bob",   "downloaded": False}]},
            ])
            mock_result = MagicMock(success=True, folder_name="P1", errors=[])
            with patch("cyberdrop.bookmarks_cmd.download_album", return_value=mock_result) as mock_dl:
                run_bookmarks(bookmarks_path=bm_path, creators_filter=["alice"], output_dir=tmpdir, no_update=True)
            self.assertEqual(mock_dl.call_count, 1)
            called_url = mock_dl.call_args[0][0]
            self.assertIn("alice", called_url)

    def test_updates_bookmarks_file_on_success(self):
        from cyberdrop.bookmarks_cmd import run_bookmarks
        with tempfile.TemporaryDirectory() as tmpdir:
            bm_path = self._make_bookmarks_file(tmpdir, [{
                "name": "Alice",
                "links": [{"name": "Pack1", "url": "https://bunkr.cr/a/abc", "downloaded": False}],
            }])
            mock_result = MagicMock(success=True, folder_name="Pack1", errors=[])
            with patch("cyberdrop.bookmarks_cmd.download_album", return_value=mock_result):
                run_bookmarks(bookmarks_path=bm_path, output_dir=tmpdir)
            with open(bm_path, encoding="utf-8") as f:
                saved = yaml.safe_load(f)
            self.assertTrue(saved["creators"][0]["links"][0]["downloaded"])


if __name__ == "__main__":
    unittest.main()
