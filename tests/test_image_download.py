from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.image_model import (
    FAL_DOWNLOAD_DOMAINS,
    MAX_IMAGE_BYTES,
    REPLICATE_DOWNLOAD_DOMAINS,
    _download_image,
    _validate_download_url,
    _write_replicate_output,
)


def response(*, status=200, headers=None, chunks=(b"image",)):
    result = MagicMock(status_code=status, headers=headers or {})
    result.__enter__.return_value = result
    result.iter_content.return_value = iter(chunks)
    return result


class ImageDownloadTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "image.png"
        # Exercise one attempt without retry delays or duplicate requests.
        retry = patch("app.image_model.retry_call", side_effect=lambda name, call: call())
        retry.start()
        self.addCleanup(retry.stop)

    def test_rejects_unsafe_destinations_before_request(self):
        urls = (
            "http://fal.media/image.png",
            "https://127.0.0.1/image.png",
            "https://169.254.169.254/latest/meta-data/",
            "https://fal.media.evil.example/image.png",
            "https://evilfal.media/image.png",
            "https://user:password@fal.media/image.png",
            "https://fal.media:8443/image.png",
            "file:///etc/passwd",
        )
        with patch("requests.get") as get:
            for url in urls:
                with self.subTest(url=url), self.assertRaises(ValueError):
                    _download_image(url, self.path, allowed_domains=FAL_DOWNLOAD_DOMAINS)
            get.assert_not_called()

    def test_accepts_provider_delivery_domains(self):
        for url, domains in (
            ("https://fal.media/image.png", FAL_DOWNLOAD_DOMAINS),
            ("https://v3b.fal.media/image.png", FAL_DOWNLOAD_DOMAINS),
            ("https://replicate.delivery/image.png", REPLICATE_DOWNLOAD_DOMAINS),
            ("https://pbxt.replicate.delivery/image.png", REPLICATE_DOWNLOAD_DOMAINS),
            ("https://delivery.replicate.com/image.png", REPLICATE_DOWNLOAD_DOMAINS),
        ):
            with self.subTest(url=url):
                _validate_download_url(url, domains)

    def test_streams_image_and_follows_validated_relative_redirect(self):
        with patch("requests.get", side_effect=[
            response(status=302, headers={"Location": "/final.png"}),
            response(chunks=(b"first", b"second")),
        ]) as get:
            _download_image("https://fal.media/start", self.path, allowed_domains=FAL_DOWNLOAD_DOMAINS)
        self.assertEqual(self.path.read_bytes(), b"firstsecond")
        self.assertEqual(get.call_args.args[0], "https://fal.media/final.png")
        self.assertFalse(get.call_args.kwargs["allow_redirects"])
        self.assertTrue(get.call_args.kwargs["stream"])

    def test_rejects_redirect_to_unapproved_host_or_http(self):
        for location in ("https://169.254.169.254/", "http://fal.media/image.png"):
            with self.subTest(location=location), patch("requests.get", return_value=response(
                status=302, headers={"Location": location},
            )) as get:
                with self.assertRaises(ValueError):
                    _download_image("https://fal.media/start", self.path, allowed_domains=FAL_DOWNLOAD_DOMAINS)
                self.assertEqual(get.call_count, 1)
        self.assertFalse(self.path.exists())

    def test_rejects_redirect_loop(self):
        with patch("requests.get", return_value=response(status=302, headers={"Location": "/loop"})):
            with self.assertRaisesRegex(ValueError, "redirect chain"):
                _download_image("https://fal.media/start", self.path, allowed_domains=FAL_DOWNLOAD_DOMAINS)

    def test_rejects_oversized_content_length(self):
        with patch("requests.get", return_value=response(headers={"Content-Length": str(MAX_IMAGE_BYTES + 1)})):
            with self.assertRaisesRegex(ValueError, "limit"):
                _download_image("https://fal.media/image.png", self.path, allowed_domains=FAL_DOWNLOAD_DOMAINS)
        self.assertEqual(list(self.path.parent.iterdir()), [])

    def test_stream_limit_preserves_existing_file_and_removes_partial_download(self):
        self.path.write_bytes(b"existing")
        with patch("app.image_model.MAX_IMAGE_BYTES", 5), patch(
            "requests.get", return_value=response(chunks=(b"123", b"456")),
        ):
            with self.assertRaisesRegex(ValueError, "limit"):
                _download_image("https://fal.media/image.png", self.path, allowed_domains=FAL_DOWNLOAD_DOMAINS)
        self.assertEqual(self.path.read_bytes(), b"existing")
        self.assertEqual(list(self.path.parent.iterdir()), [self.path])

    def test_replicate_url_strings_and_file_outputs_use_checked_downloader(self):
        url = "https://replicate.delivery/image.png"
        sdk_output = SimpleNamespace(url=url, read=MagicMock())
        for output in (url, sdk_output, SimpleNamespace(url=lambda: url)):
            with self.subTest(output=output), patch("requests.get", return_value=response()):
                _write_replicate_output([output], self.path)
                self.assertEqual(self.path.read_bytes(), b"image")
        sdk_output.read.assert_not_called()


if __name__ == "__main__":
    unittest.main()
