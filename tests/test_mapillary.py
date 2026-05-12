import unittest
from unittest.mock import patch

from road_damage_kz.mapillary import (
    collect_mapillary_bbox,
    creator_name,
    format_captured_at,
    manifest_row_from_mapillary_image,
    parse_bbox,
    split_bbox,
)


class MapillaryTests(unittest.TestCase):
    def test_parse_bbox_validates_shape_and_order(self):
        self.assertEqual(parse_bbox("76.7,43.1,77.1,43.4"), (76.7, 43.1, 77.1, 43.4))
        with self.assertRaises(ValueError):
            parse_bbox("77.1,43.1,76.7,43.4")

    def test_split_bbox_tiles_area(self):
        tiles = split_bbox((0.0, 0.0, 2.0, 2.0), grid_size=2)

        self.assertEqual(len(tiles), 4)
        self.assertEqual(tiles[0], (0.0, 0.0, 1.0, 1.0))
        self.assertEqual(tiles[-1], (1.0, 1.0, 2.0, 2.0))

    def test_creator_name_prefers_username_with_id(self):
        self.assertEqual(
            creator_name({"username": "road_user", "id": "42"}),
            "road_user (Mapillary user 42)",
        )
        self.assertEqual(creator_name({"id": "42"}), "Mapillary user 42")

    def test_format_captured_at_handles_mapillary_milliseconds(self):
        self.assertEqual(format_captured_at(1704067200000), "2024-01-01")

    def test_manifest_row_from_mapillary_image_is_license_ready_but_privacy_unchecked(self):
        row = manifest_row_from_mapillary_image(
            {
                "id": "123",
                "captured_at": 1704067200000,
                "computed_geometry": {"type": "Point", "coordinates": [76.9, 43.2]},
                "creator": {"username": "road_user", "id": "42"},
                "is_pano": False,
                "thumb_1024_url": "https://images.mapillary.example/123.jpg",
            },
            bbox=(76.7, 43.1, 77.1, 43.4),
            city="almaty",
            region="Almaty",
        )

        self.assertIsNotNone(row)
        self.assertEqual(row["image_id"], "mapillary_123")
        self.assertEqual(row["source_url"], "https://www.mapillary.com/app/?pKey=123")
        self.assertEqual(row["license"], "CC-BY-SA-4.0")
        self.assertEqual(row["license_ok"], "true")
        self.assertEqual(row["privacy_checked"], "false")
        self.assertIn("city:almaty", row["capture_context"])
        self.assertIn("Mapillary states imagery", row["notes"])

    def test_collect_mapillary_bbox_paginates_results(self):
        first_payload = {
            "data": [
                {
                    "id": "one",
                    "creator": {"username": "a"},
                    "thumb_1024_url": "https://images.example/one.jpg",
                }
            ],
            "paging": {"cursors": {"after": "cursor"}},
        }
        second_payload = {
            "data": [
                {
                    "id": "two",
                    "creator": {"username": "b"},
                    "thumb_1024_url": "https://images.example/two.jpg",
                }
            ],
            "paging": {},
        }

        with patch("road_damage_kz.mapillary._api_get", side_effect=[first_payload, second_payload]):
            rows = collect_mapillary_bbox((76.7, 43.1, 77.1, 43.4), access_token="token", limit=2)

        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["image_id"], "mapillary_one")

    def test_collect_mapillary_bbox_continues_after_tile_timeout(self):
        failed_payload = RuntimeError("Mapillary API request failed with HTTP 500")
        good_payload = {
            "data": [
                {
                    "id": "one",
                    "creator": {"username": "a"},
                    "thumb_1024_url": "https://images.example/one.jpg",
                }
            ],
            "paging": {},
        }

        with patch("road_damage_kz.mapillary._api_get", side_effect=[failed_payload, good_payload]):
            rows = collect_mapillary_bbox(
                (76.7, 43.1, 77.1, 43.4),
                access_token="token",
                limit=1,
                grid_size=2,
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["image_id"], "mapillary_one")


if __name__ == "__main__":
    unittest.main()
