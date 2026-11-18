"""Public-source parsing and last-good-data safeguards; no network calls."""
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("sowhat_archive_sync", Path(__file__).parents[1] / "sowhat_archive_sync.py")
archive = importlib.util.module_from_spec(spec)
spec.loader.exec_module(archive)


class ArchiveTests(unittest.TestCase):
    def test_only_public_issue_links_and_real_dates(self):
        html = '''<a href="https://stib.ee/abc">A &amp; B <time>2026. 11. 18.</time></a>
        <a href="https://stib.ee/abc">duplicate 2026. 11. 18.</a>
        <a href="https://page.stibee.com/subscriptions/479387">Subscribe</a>'''
        self.assertEqual(archive.parse_archive(html), [{"id": "abc", "url": "https://stib.ee/abc", "date": "2026-11-18", "title": "A & B"}])

    def test_uses_editorial_og_image_instead_of_first_logo(self):
        html = '<meta content="https://img2.stibee.com/editorial.jpg" property="og:image"><img src="logo.png"><p>Vol. 115 ' + 'Newsletter content ' * 6 + '</p>'
        self.assertEqual(archive.parse_letter(html), {"image": "https://img2.stibee.com/editorial.jpg", "volume": 115})

    def test_rejects_untrusted_or_missing_image_without_inventing_cover(self):
        html = '<meta property="og:image" content="javascript:alert(1)"><p>' + 'Newsletter ' * 10 + '</p>'
        self.assertEqual(archive.parse_letter(html)["image"], "")
        with self.assertRaises(ValueError):
            archive.parse_archive('<p>Temporary error</p>')

    def test_failed_refresh_preserves_successful_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest = Path(temp) / 'archive.json'
            status = Path(temp) / 'status.json'
            old = {"items": [{"id": "abc", "title": "Published issue"}]}
            archive.write_json(manifest, old)
            before = manifest.read_bytes()
            with patch.object(archive, 'MANIFEST', manifest), patch.object(archive, 'STATUS', status), patch.object(archive, 'get_html', return_value='<p>Error</p>'):
                with self.assertRaises(ValueError):
                    archive.synchronize(force=True)
            self.assertEqual(manifest.read_bytes(), before)

    def test_new_publication_is_added_with_its_own_representative_image(self):
        with tempfile.TemporaryDirectory() as temp:
            manifest, status = Path(temp) / 'archive.json', Path(temp) / 'status.json'
            archive.write_json(manifest, {'items':[{'id':'old','url':'https://stib.ee/old','date':'2026-11-17','title':'Old issue','image':'https://img2.stibee.com/old.jpg','volume':114}]})
            def source(url):
                if url == archive.ARCHIVE_URL:
                    return '<a href="https://stib.ee/new">New issue 2026. 11. 18.</a><a href="https://stib.ee/old">Old issue 2026. 11. 17.</a>'
                issue = url.rsplit('/',1)[-1]
                return f'<meta property="og:image" content="https://img2.stibee.com/{issue}.jpg"><img src="logo.png"><p>Vol. {115 if issue == "new" else 114} ' + 'Newsletter content ' * 8 + '</p>'
            with patch.object(archive,'MANIFEST',manifest), patch.object(archive,'STATUS',status), patch.object(archive,'get_html',side_effect=source):
                result = archive.synchronize(force=True)
            saved = archive.read_json(manifest,{})['items']
            self.assertEqual(result['count'],2)
            self.assertEqual((saved[0]['id'],saved[0]['image'],saved[0]['volume']),('new','https://img2.stibee.com/new.jpg',115))


if __name__ == '__main__':
    unittest.main()
