"""
Unit tests for content extraction and boilerplate stripping.
"""

from app.services.extractor import extract_content_from_html


def test_extract_content_and_clean_boilerplate():
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NASA - James Webb Space Telescope</title>
        <script>console.log("malicious code or tracker");</script>
        <style>.body { background: black; }</style>
    </head>
    <body>
        <nav><a href="/home">Home</a> | <a href="/about">About</a></nav>
        <header>Site Header</header>
        <main>
            <h1>James Webb Space Telescope Launch</h1>
            <p>The James Webb Space Telescope was successfully launched into space on December 25, 2021 from Kourou, French Guiana.</p>
            <p>It is NASA's flagship infrared space observatory, designed to succeed the Hubble Space Telescope.</p>
        </main>
        <aside class="sidebar-widget">Advertisement banner</aside>
        <footer>Copyright 2026 NASA</footer>
    </body>
    </html>
    """

    doc = extract_content_from_html(html)

    assert doc.title == "NASA - James Webb Space Telescope"
    assert len(doc.paragraphs) >= 2
    assert any("December 25, 2021" in p for p in doc.paragraphs)
    assert "malicious code" not in doc.full_text
    assert "Advertisement banner" not in doc.full_text
    assert "Copyright 2026" not in doc.full_text


def test_extract_empty_or_malformed():
    doc = extract_content_from_html("")
    assert doc.paragraphs == []
    assert doc.word_count == 0
