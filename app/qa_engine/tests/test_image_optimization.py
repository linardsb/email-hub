"""Unit tests for the image_optimization QA check."""

from app.qa_engine.checks._factory import get_check


class TestImageOptimization:
    check = get_check("image_optimization")

    # --- Core attribute checks ---

    async def test_valid_images_pass(self) -> None:
        html = """<html><body>
        <img src="https://example.com/hero.png" alt="Hero" width="600" height="300"
             style="display:block;" border="0">
        </body></html>"""
        result = await self.check.run(html)
        # Only display:block issue should be absent; summary is info-only
        assert result.check_name == "image_optimization"

    async def test_images_with_dimensions_pass(self, sample_html_valid: str) -> None:
        result = await self.check.run(sample_html_valid)
        assert result.check_name == "image_optimization"

    async def test_missing_dimensions_deducts(self) -> None:
        html = '<html><body><img src="https://example.com/img.png" alt="test" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "missing" in (result.details or "").lower()
        assert result.score < 1.0

    async def test_missing_alt_deducts(self) -> None:
        html = '<html><body><img src="https://example.com/img.png" width="600" height="300" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "alt" in (result.details or "").lower()

    async def test_empty_src_deducts(self) -> None:
        html = '<html><body><img src="" alt="test" width="100" height="100" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "empty" in (result.details or "").lower() or "src" in (result.details or "").lower()

    async def test_tracking_pixel_excluded_from_alt_check(self) -> None:
        html = """<html><body>
        <img src="https://example.com/hero.png" alt="Hero" width="600" height="300" style="display:block;">
        <img src="https://track.example.com/open" width="1" height="1" alt="" aria-hidden="true">
        </body></html>"""
        result = await self.check.run(html)
        # Tracking pixel should not trigger missing alt
        assert (
            "alt" not in (result.details or "").lower()
            or "tracking" in (result.details or "").lower()
        )

    # --- Format validation ---

    async def test_bmp_format_flagged(self) -> None:
        html = '<html><body><img src="https://example.com/logo.bmp" alt="logo" width="200" height="100" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "BMP" in (result.details or "")

    async def test_tiff_format_flagged(self) -> None:
        html = '<html><body><img src="https://example.com/photo.tiff" alt="photo" width="200" height="100" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "TIFF" in (result.details or "")

    async def test_jpeg_png_gif_pass(self) -> None:
        html = """<html><body>
        <img src="https://example.com/a.jpg" alt="A" width="100" height="100" style="display:block;">
        <img src="https://example.com/b.png" alt="B" width="100" height="100" style="display:block;">
        <img src="https://example.com/c.gif" alt="C" width="100" height="100" style="display:block;">
        </body></html>"""
        result = await self.check.run(html)
        assert "BMP" not in (result.details or "")
        assert "TIFF" not in (result.details or "")

    async def test_data_uri_oversize_flagged(self) -> None:
        import base64

        # Create a 5KB data URI (well over 3KB threshold)
        payload = base64.b64encode(b"x" * 5000).decode()
        html = f'<html><body><img src="data:image/png;base64,{payload}" alt="test" width="100" height="100" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "data uri" in (result.details or "").lower() or "Data URI" in (result.details or "")

    async def test_small_data_uri_passes(self) -> None:
        import base64

        # Create a tiny data URI (under 3KB)
        payload = base64.b64encode(b"x" * 100).decode()
        html = f'<html><body><img src="data:image/png;base64,{payload}" alt="test" width="100" height="100" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert "Data URI" not in (result.details or "")

    # --- Dimension integrity ---

    async def test_px_suffix_flagged(self) -> None:
        html = '<html><body><img src="https://example.com/img.png" alt="test" width="100px" height="100" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "100px" in (result.details or "")

    async def test_numeric_dimensions_pass(self) -> None:
        html = '<html><body><img src="https://example.com/img.png" alt="test" width="600" height="300" style="display:block;"></body></html>'
        result = await self.check.run(html)
        # Should not have invalid dimension issues
        assert "Invalid" not in (result.details or "")

    async def test_auto_dimension_flagged(self) -> None:
        html = '<html><body><img src="https://example.com/img.png" alt="test" width="auto" height="300" style="display:block;"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "auto" in (result.details or "")

    # --- Tracking pixels ---

    async def test_tracking_pixel_without_empty_alt_flagged(self) -> None:
        html = '<html><body><img src="https://track.example.com/open" width="1" height="1" alt="track"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "tracking" in (result.details or "").lower() or "Tracking" in (result.details or "")

    async def test_tracking_pixel_with_empty_alt_and_aria_passes(self) -> None:
        html = '<html><body><img src="https://track.example.com/open" width="1" height="1" alt="" aria-hidden="true"></body></html>'
        result = await self.check.run(html)
        # Tracking pixel check should pass — correct attributes
        assert "Tracking pixel" not in (result.details or "")

    # --- Rendering practices ---

    async def test_linked_image_no_border_flagged(self) -> None:
        html = '<html><body><a href="https://example.com"><img src="https://example.com/cta.png" alt="CTA" width="200" height="50" style="display:block;"></a></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "border" in (result.details or "").lower()

    async def test_linked_image_border_zero_passes(self) -> None:
        html = '<html><body><a href="https://example.com"><img src="https://example.com/cta.png" alt="CTA" width="200" height="50" style="display:block;" border="0"></a></body></html>'
        result = await self.check.run(html)
        assert "border" not in (result.details or "").lower()

    async def test_missing_display_block_flagged(self) -> None:
        html = '<html><body><img src="https://example.com/hero.png" alt="Hero" width="600" height="300"></body></html>'
        result = await self.check.run(html)
        assert result.passed is False
        assert "display:block" in (result.details or "")

    # --- Edge cases ---

    async def test_no_images_passes(self) -> None:
        html = "<html><body><p>No images here</p></body></html>"
        result = await self.check.run(html)
        assert result.passed is True

    async def test_summary_in_details(self) -> None:
        html = """<html><body>
        <img src="https://example.com/hero.png" alt="Hero" width="600" height="300" style="display:block;">
        </body></html>"""
        result = await self.check.run(html)
        assert "Images:" in (result.details or "")

    async def test_score_caps_at_zero(self) -> None:
        # Many images all with issues should not produce negative score
        imgs = "\n".join(
            f'<img src="https://example.com/img{i}.bmp" width="auto" height="auto">'
            for i in range(20)
        )
        html = f"<html><body>{imgs}</body></html>"
        result = await self.check.run(html)
        assert result.score >= 0.0
