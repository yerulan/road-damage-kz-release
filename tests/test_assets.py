from pathlib import Path
import tempfile
import unittest

from road_damage_kz.assets import (
    commons_thumbnail_url,
    download_candidates,
    extension_from_url,
    generate_local_gallery,
    sha256_bytes,
)


class AssetsTests(unittest.TestCase):
    def test_extension_from_url_normalizes_jpeg(self):
        self.assertEqual(extension_from_url("https://example.com/image.jpeg"), ".jpg")
        self.assertEqual(extension_from_url("https://example.com/image.png"), ".png")
        self.assertEqual(extension_from_url("https://example.com/no-extension"), ".jpg")

    def test_sha256_bytes_is_stable(self):
        digest = sha256_bytes(b"abc")
        self.assertEqual(digest, "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")

    def test_commons_thumbnail_url_builds_thumb_path(self):
        url = "https://upload.wikimedia.org/wikipedia/commons/3/3c/P-11_Road_in_Kazakhstan.jpg"
        thumb = commons_thumbnail_url(url, 960)
        self.assertEqual(
            thumb,
            "https://upload.wikimedia.org/wikipedia/commons/thumb/3/3c/P-11_Road_in_Kazakhstan.jpg/960px-P-11_Road_in_Kazakhstan.jpg",
        )

    def test_generate_local_gallery_uses_cache_manifest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "image.jpg"
            image.write_bytes(b"fake")
            cache = root / "local_files.csv"
            output = root / "gallery.html"
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                f"commons_1,https://example.com/file,https://example.com/file.jpg,{image},abc,4,downloaded,\n",
                encoding="utf-8",
            )

            summary = generate_local_gallery(cache, output)

            self.assertEqual(summary["rows"], 1)
            self.assertIn("commons_1", output.read_text(encoding="utf-8"))

    def test_download_candidates_skips_failed_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            triage = root / "triage.csv"
            cache = root / "local_files.csv"
            output_dir = root / "raw"
            triage.write_text(
                "image_id,source_url,download_url,license,author,capture_context,damage_labels,"
                "license_ok,privacy_checked,is_photo_candidate,road_surface_visible,"
                "target_damage_visible,privacy_ok,recommended_action,reviewer,notes\n"
                "commons_1,https://example.com/file,https://example.com/file.jpg,CC-BY-4.0,"
                "Author,commons,unknown,true,false,true,,,,,,\n",
                encoding="utf-8",
            )
            cache.write_text(
                "image_id,source_url,download_url,local_path,sha256,bytes,status,error\n"
                "commons_1,https://example.com/file,https://example.com/file.jpg,"
                "data/raw/candidates/commons_1.jpg,,0,failed,HTTP 429\n",
                encoding="utf-8",
            )

            summary = download_candidates(triage, output_dir, cache, limit=10)

            self.assertEqual(summary["candidates"], 0)
            self.assertEqual(summary["skipped_failed_cache"], 1)


if __name__ == "__main__":
    unittest.main()
