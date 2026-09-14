"""Editorial and presentation checks; never use real buyers or prices."""

from pathlib import Path
import re

import pytest
from flask import render_template

from conftest import login_admin
from tianwai.commerce import PRICING_BATCH_SLUGS
from tianwai.db import get_db
from tianwai.release_packages import get_release_package


@pytest.mark.parametrize('slug', PRICING_BATCH_SLUGS)
def test_each_private_package_has_substantive_content_and_matches_reader(app, client, slug):
    login_admin(client)
    with app.app_context():
        idea = dict(get_db().execute('SELECT * FROM ideas WHERE slug = ?', (slug,)).fetchone())
        package = get_release_package(slug)
        assert package is not None
        assert len(re.findall(r'[\u4e00-\u9fff]', str(package))) >= 1500
        assert len({step['title'] for step in package['flow_steps']}) == 6
        for sheet in package['worksheets']:
            assert len(sheet['rows']) >= 3
            assert all(len(row) == len(sheet['columns']) for row in sheet['rows'])
        with app.test_request_context('/'):
            reader = render_template('order_access.html', order={**idea, 'idea_id': idea['id'], 'idea_slug': slug},
                                     access_context={'customer': '合成閱讀者', 'order': '合成閱卷', 'time': '合成時間'},
                                     concept_guide=None)
    preview = client.get(f"/admin/ideas/{idea['id']}/preview")
    assert preview.status_code == 200
    preview_text = preview.get_data(as_text=True)
    for section in ['release-flow', 'release-specs', 'release-mvp', 'release-tests', 'release-worksheets', 'release-handoff']:
        assert f'id="{section}"' in reader
        assert f'id="{section}"' in preview_text
    assert package['flow_steps'][0]['title'] in reader and package['flow_steps'][0]['title'] in preview_text
    assert '管理員專用' in preview_text
    assert '/admin/ideas/' not in reader
    assert '/library/assets/' in reader
    assert '/library/assets/' not in preview_text
    assert 'private_assets/' not in reader + preview_text
    public = client.get(f'/ideas/{slug}').get_data(as_text=True)
    assert package['flow_steps'][0]['body'] not in public
    assert 'release-worksheets' not in public


def test_release_hub_has_no_price_form_in_normal_controls(client):
    login_admin(client)
    html = client.get('/admin').get_data(as_text=True)
    normal = html.split('id="release-hub"', 1)[1].split('<details class="release-maintenance">', 1)[0]
    assert '全部上架（13 案）' in normal
    assert '<input' not in normal and '<select' not in normal
    assert 'id="release-cards"' in normal
    assert '<details class="release-maintenance" open' not in html
    source = Path('static/v38-release.js').read_text(encoding='utf-8')
    assert "'X-CSRF-Token': csrf" in source
    assert 'confirm_publication: true' in source
    assert "fetch('/api/orders'" not in source
    assert 'release_ready: true' not in source
    assert 'localStorage' not in source and 'console.log' not in source
