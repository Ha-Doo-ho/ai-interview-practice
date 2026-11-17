"""Supplied frontend mounting; run only through tools.run_checks."""
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import create_app
from completion_helpers import HEADERS,send,finish_one_main_round,finish_required_stages
from uuid import uuid4
import json
import pytest
from html.parser import HTMLParser
from urllib.parse import parse_qs, urljoin, urlparse

def test_supplied_html_and_same_origin_assets_are_served(tmp_path):
    app=create_app(f"sqlite:///{tmp_path/'frontend.db'}")
    try:
        with TestClient(app) as c:
            root=c.get('/')
            assert root.status_code==200
            assert root.content==Path('html/index.html').read_bytes()
            class LocalAssets(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.paths = []
                    self.urls = []

                def handle_starttag(self, tag, attributes):
                    attributes = dict(attributes)
                    resource = attributes.get('src') if tag == 'script' else (
                        attributes.get('href') if tag == 'link' and attributes.get('rel') == 'stylesheet' else None
                    )
                    if resource and not urlparse(resource).netloc:
                        self.paths.append(urlparse(urljoin('http://testserver/', resource)).path)
                        self.urls.append(resource)

            assets = LocalAssets()
            assets.feed(root.text)
            assert assets.paths.index('/frontend/client.js') < assets.paths.index('/frontend/auth.js') < assets.paths.index('/frontend/script.js')
            assert assets.paths.index('/frontend/client.js') < assets.paths.index('/frontend/script.js')
            assert assets.paths.index('/frontend/script.js') < assets.paths.index('/frontend/practice.js')
            assert assets.paths.index('/frontend/practice.js') < assets.paths.index('/frontend/games.js')
            assert assets.paths.index('/frontend/games.js') < assets.paths.index('/frontend/interview.js')
            assert assets.paths.index('/frontend/interview.js') < assets.paths.index('/frontend/report.js')
            assert 'scoreAdapt' not in root.text and 'scoreInterview' not in root.text
            assert 'onclick="finalizeRun()"' not in root.text
            assert 'report-analyze' in root.text and 'report-content' in root.text
            # A new page must not reuse the older, incompatible JS URLs from cache.
            versions = [parse_qs(urlparse(asset).query).get('v', [''])[0] for asset in assets.urls]
            assert versions and all(versions) and len(set(versions)) == 1
            for asset in assets.urls:
                response = c.get(asset)
                assert response.status_code == 200, asset
                assert response.content == Path('html', Path(urlparse(asset).path).name).read_bytes()
            definitions = c.get('/api/definitions').json()
            survey_fixture = json.loads(Path('tests/fixtures/survey_definitions.json').read_text(encoding='utf-8'))
            assert survey_fixture == {'version': definitions['version'], 'surveys': definitions['surveys']}
            for filename in ['script.js','client.js','auth.js','practice.js','games.js','interview.js','report.js','style.css']:
                response=c.get('/frontend/'+filename)
                assert response.status_code==200
                assert response.content==Path('html',filename).read_bytes()
            assert c.get('/static/index.html').status_code==200
    finally: app.state.store.engine.dispose()


@pytest.mark.scenario('SCN-012')
def test_auth_session_register_restore_logout_login_and_revocation(tmp_path):
    app = create_app(f"sqlite:///{tmp_path/'auth-session.db'}")
    credentials = {'username': 'auth-synthetic', 'password': ' synthetic-password '}
    try:
        with TestClient(app) as client:
            assert client.get('/api/me').status_code == 401
            created = client.post('/api/register', headers=HEADERS, json=credentials)
            assert created.status_code == 201
            user = created.json()
            assert set(user) == {'user_id', 'username'}
            assert user['username'] == credentials['username']
            assert 'httponly' in created.headers['set-cookie'].lower()
            assert 'samesite=strict' in created.headers['set-cookie'].lower()
            for _ in range(2):
                assert client.get('/api/me').json() == user
            duplicate = client.post('/api/register', headers=HEADERS, json=credentials)
            assert duplicate.status_code == 409
            assert duplicate.json() == {'error': 'username_taken'}
            token = client.cookies.get('interview_session')
            assert client.post('/api/logout').status_code == 403
            assert client.get('/api/me').json() == user
            assert client.post('/api/logout', headers=HEADERS).status_code == 204
            assert client.get('/api/me').status_code == 401
            assert client.cookies.get('interview_session') is None
            with TestClient(app) as replay:
                assert replay.get('/api/me', headers={'Cookie': f'interview_session={token}'}).status_code == 401
            wrong = client.post('/api/login', headers=HEADERS, json={**credentials, 'password': 'wrong-password'})
            assert wrong.status_code == 401 and wrong.json() == {'error': 'invalid_credentials'}
            assert client.get('/api/me').status_code == 401
            login = client.post('/api/login', headers=HEADERS, json=credentials)
            assert login.status_code == 200
            assert login.json() == user
            assert client.get('/api/me').json() == user
            assert client.cookies.get('interview_session') != token
    finally:
        app.state.store.engine.dispose()

def test_generated_client_payloads_mock_report_resume_and_owned_delete(tmp_path):
    fixture=json.loads(Path('tests/fixtures/frontend_client_payloads.json').read_text(encoding='utf-8'))
    app=create_app(f"sqlite:///{tmp_path/'client-journey.db'}")
    try:
        with TestClient(app) as c:
            auth=c.post('/api/register',headers=HEADERS,json={'username':'astra-synthetic','password':'synthetic-password'})
            assert auth.status_code==201 and 'httponly' in auth.headers['set-cookie'].lower()
            r=c.post('/api/runs',headers=HEADERS,json={}).json()
            for payload in fixture['surveys']:r=send(c,r,'surveys',**payload)
            records={x['item_id']:x for x in r['records']}
            assert records['O-B01']['data']['selected_position']==6
            assert 'selected_position' not in records['O-B02']['data']
            assert records['P-B01']['data']['self']['selected_position']==4
            assert records['P-B01']['data']['imagined_others']['status']=='timed_out'
            assert records['S-B02']['data']['final_value']==0
            assert records['S-B02']['data']['explicit_confirmation'] is True
            assert records['S-B02']['data']['interaction_occurred'] is False
            assert [x['option_id'] for x in records['R-UNMAPPED']['data']['ranked_selection']]==['helping','growth','autonomy']
            questions=[q for q in r['questions'] if q['question_mode']=='baseline']
            payload={**fixture['answer'],'question_id':questions[0]['question_id'],'expected_revision':r['revision'],'idempotency_key':str(uuid4())}
            first=c.post(f"/api/runs/{r['run_id']}/answers",headers=HEADERS,json=payload)
            assert first.status_code==200
            assert c.post(f"/api/runs/{r['run_id']}/answers",headers=HEADERS,json=payload).json()==first.json()
            r=first.json();old=r['records'][-1]['data']
            assert old['text']==fixture['answer']['text'] and old['question_text_snapshot']==questions[0]['question_text']
            r=send(c,r,'answers',question_id=questions[0]['question_id'],text='  수정 원문 🐱\n',status='asked_answered',replaces_answer_id=old['answer_id'],expected_answer_version=old['answer_version'])
            assert r['records'][-1]['data']['answer_version']=='2.0.0'
            assert next(x['data'] for x in r['records'] if x['data'].get('answer_id')==old['answer_id'])==old
            for question,status in zip(questions[1:],['asked_no_text','skipped']):r=send(c,r,'answers',question_id=question['question_id'],text='',status=status)
            response=c.post(f"/api/runs/{r['run_id']}/analyze",headers=HEADERS,json={'expected_revision':r['revision'],'idempotency_key':str(uuid4())})
            assert response.status_code==409 and response.json()['error']=='main_round_completion_required'
            assert c.get(f"/api/runs/{r['run_id']}").json()==r
            # Only synthetic HTTP fixture setup performs game actions, never new HTML.
            r=finish_one_main_round(c,r);r=send(c,r,'analyze')
            assert r['report_draft']['runtime_mode']=='mock' and r['report'] is None
            assert len(r['report_draft']['cards'])==3
            for card in r['report_draft']['cards']:
                for span in card['interview_evidence']:
                    text=next(x['data']['text'] for x in r['records'] if x['data'].get('answer_id')==span['source_id'] and x['data'].get('answer_version')==span['source_version'])
                    assert text[span['start']:span['end']]==span['quote']
            response=c.post(f"/api/runs/{r['run_id']}/finalize",headers=HEADERS,json={'expected_revision':r['revision'],'idempotency_key':str(uuid4())})
            assert response.status_code==409 and response.json()['error']=='game_completion_required'
            r=finish_required_stages(c,r);r=send(c,r,'finalize')
            assert r['status']=='completed' and r['report']['runtime_mode']=='mock'
            assert c.post('/api/logout',headers=HEADERS,json={}).status_code==204
            assert c.get(f"/api/runs/{r['run_id']}").status_code==401
            assert c.post('/api/register',headers=HEADERS,json={'username':'astra-other','password':'synthetic-password'}).status_code==201
            assert c.get(f"/api/runs/{r['run_id']}").status_code==404
            assert c.delete(f"/api/runs/{r['run_id']}",headers=HEADERS).status_code==404
            c.post('/api/logout',headers=HEADERS,json={})
            assert c.post('/api/login',headers=HEADERS,json={'username':'astra-synthetic','password':'synthetic-password'}).status_code==200
            assert c.get(f"/api/runs/{r['run_id']}").json()==r
            assert any(x['run_id']==r['run_id'] for x in c.get('/api/runs').json()['runs'])
            assert c.delete(f"/api/runs/{r['run_id']}",headers=HEADERS).status_code==204
            assert c.get(f"/api/runs/{r['run_id']}").status_code==404
            assert c.get('/api/runs').json()=={'runs':[]}
    finally: app.state.store.engine.dispose()
