from pathlib import Path
import tempfile
import unittest

from road_damage_kz.external import check_rdd_readiness, import_rdd_voc_dataset, labels_from_voc_xml, rdd_download_script


VOC_XML = """<annotation>
  <filename>sample.jpg</filename>
  <size><width>100</width><height>50</height><depth>3</depth></size>
  <object>
    <name>D00</name>
    <bndbox><xmin>10</xmin><ymin>5</ymin><xmax>50</xmax><ymax>25</ymax></bndbox>
  </object>
  <object>
    <name>D40</name>
    <bndbox><xmin>60</xmin><ymin>10</ymin><xmax>90</xmax><ymax>40</ymax></bndbox>
  </object>
  <object>
    <name>D99</name>
    <bndbox><xmin>1</xmin><ymin>1</ymin><xmax>2</xmax><ymax>2</ymax></bndbox>
  </object>
</annotation>
"""


class ExternalDatasetTests(unittest.TestCase):
    def test_check_rdd_readiness_reports_missing_root(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = check_rdd_readiness(Path(directory) / "missing")

        self.assertEqual(summary["status"], "missing_root")
        self.assertEqual(summary["usable_images"], 0)

    def test_rdd_download_script_contains_selected_official_archives(self):
        script = rdd_download_script(["india", "czech"], Path("data/external/RDD2022"))

        self.assertIn("RDD2022_India.zip", script)
        self.assertIn("RDD2022_Czech.zip", script)
        self.assertIn("curl -fL", script)
        self.assertIn("unzip -t", script)
        self.assertIn("roadkz check-rdd", script)

    def test_check_rdd_readiness_reports_no_xml(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = check_rdd_readiness(Path(directory))

        self.assertEqual(summary["status"], "no_xml")
        self.assertEqual(summary["xml_files"], 0)

    def test_check_rdd_readiness_reports_unmatched_images(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "sample.xml").write_text(VOC_XML, encoding="utf-8")

            summary = check_rdd_readiness(root)

        self.assertEqual(summary["status"], "no_usable_annotations")
        self.assertEqual(summary["matched_images"], 0)

    def test_check_rdd_readiness_counts_valid_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annotations = root / "Annotations"
            images = root / "JPEGImages"
            annotations.mkdir()
            images.mkdir()
            (annotations / "sample.xml").write_text(VOC_XML, encoding="utf-8")
            (images / "sample.jpg").write_bytes(b"fake image bytes")

            summary = check_rdd_readiness(root)

        self.assertEqual(summary["status"], "ready")
        self.assertEqual(summary["usable_images"], 1)
        self.assertEqual(summary["boxes"], 2)
        self.assertEqual(summary["class_distribution"]["pothole"], 1)

    def test_labels_from_voc_xml_maps_rdd_classes(self):
        with tempfile.TemporaryDirectory() as directory:
            xml_path = Path(directory) / "sample.xml"
            xml_path.write_text(VOC_XML, encoding="utf-8")

            labels = labels_from_voc_xml(xml_path)

        self.assertEqual(labels[0], "0 0.300000 0.300000 0.400000 0.400000")
        self.assertEqual(labels[1], "3 0.750000 0.500000 0.300000 0.600000")
        self.assertEqual(len(labels), 2)

    def test_import_rdd_voc_dataset_writes_yolo_dataset(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            annotations = root / "Annotations"
            images = root / "JPEGImages"
            output = root / "out"
            annotations.mkdir()
            images.mkdir()
            (annotations / "sample.xml").write_text(VOC_XML, encoding="utf-8")
            (images / "sample.jpg").write_bytes(b"fake image bytes")

            summary = import_rdd_voc_dataset(
                root,
                output,
                val_ratio=0.0,
                copy_mode="copy",
            )

            self.assertEqual(summary["imported"], 1)
            self.assertEqual(summary["boxes"], 2)
            self.assertEqual(summary["train"] + summary["val"], 1)
            self.assertTrue((output / "import_summary.json").exists())
            self.assertTrue((output / "dataset.yaml").exists())
            label_files = list((output / "labels").rglob("sample.txt"))
            self.assertEqual(len(label_files), 1)
            self.assertIn("3 0.750000", label_files[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
