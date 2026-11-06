"""Run ONLY against isolated local test fixture, through the HTTPS Vite proxy.
PYTHONPATH=backend <backend-venv>/bin/python web/scripts/integration-http.py
Uses checked-in synthetic test accounts, never a user's login.
"""
import asyncio
import json
import os
import ssl
from pathlib import Path
import httpx
from tests.conftest import PASSWORDS
from tests.samples import invoice_pdf

def check(condition):
    if not condition:
        raise RuntimeError('Integration check failed')


async def main():
    root = Path(__file__).resolve().parents[2]
    tls = ssl.create_default_context(cafile=str(root / 'web/node_modules/.vite/basic-ssl/_cert.pem'))
    results = {}
    async with httpx.AsyncClient(base_url='https://localhost:5173', verify=tls, timeout=120) as c:
        c.headers['Origin'] = 'https://localhost:5173'
        response = await c.post('/api/v1/auth/login', json={'username': 'reviewer', 'password': PASSWORDS['reviewer']})
        check(response.status_code == 200)
        check('access_token' not in response.json() and 'refresh_token' not in response.json())
        cookies = response.headers.get_list('set-cookie')
        check(len(cookies) == 3)
        check(all(('Secure' in cookie and 'SameSite=strict' in cookie for cookie in cookies)))
        check(sum(('HttpOnly' in cookie for cookie in cookies)) == 2)
        results['login'] = '200; no tokens in JSON; Secure+SameSite=Strict; two HttpOnly cookies'
        check((await c.get('/api/v1/auth/me')).status_code == 200)
        results['me'] = 200
        denied = await c.post('/api/v1/documents', files={'file': ('invoice.pdf', invoice_pdf(2), 'application/pdf')})
        check(denied.status_code == 403 and denied.json()['code'] == 'CSRF_FAILED')
        results['missing_csrf'] = '403 CSRF_FAILED'
        c.headers['X-CSRF-Token'] = c.cookies['csrf_token']
        response = await c.post('/api/v1/documents', files={'file': ('invoice.pdf', invoice_pdf(2), 'application/pdf')}, data={'doc_type': 'commercial_invoice'})
        check(response.status_code == 202)
        document_id = response.json()['id']
        results['upload'] = '202; actual multipart PDF'
        if os.environ.get('M1_INTEGRATION_DIR'):
            transport = json.loads((Path(os.environ['M1_INTEGRATION_DIR']) / 'transport.json').read_text())
            check(transport == {'origin': 'https://localhost:5173', 'host': 'localhost:5173', 'forwarded_proto': 'https'})
            results['proxy_origin'] = transport
        for _ in range(180):
            document = (await c.get(f'/api/v1/documents/{document_id}')).json()
            if document['status'] in ('ready', 'failed'):
                break
            await asyncio.sleep(1)
        check(document['status'] == 'ready' and document['pages'] == 2)
        results['poll'] = 'ready; 2 pages; progress 100'
        recognition = (await c.get(f'/api/v1/documents/{document_id}/recognition')).json()
        blocks = recognition['ocr']['blocks']
        check({b['page'] for b in blocks} == {1, 2})
        check('INVOICE' in ' '.join((b['text'] for b in blocks)).upper())
        check(all((len(b['bbox']) == 4 and all((0 <= v <= 1 for v in b['bbox'])) for b in blocks)))
        results['ocr'] = f'200; real RapidOCR; {len(blocks)} normalized blocks across pages 1/2'
        results['fields'] = f"{len(recognition['fields'])} fields returned by baseline backend"
        for page in (1, 2):
            image = await c.get(f'/api/v1/documents/{document_id}/pages/{page}/image')
            check(image.status_code == 200 and image.content.startswith(b'\x89PNG'))
            check(image.headers['cache-control'] == 'no-store')
        results['images'] = '200 on pages 1/2; real PNG; Cache-Control no-store'
        fields = await c.patch(f'/api/v1/documents/{document_id}/fields', json={'version': 1, 'fields': [{'key': 'invoice_no', 'value': 'test'}]})
        results['patch_fields'] = fields.status_code
        review = await c.post('/api/v1/reviews', json={'document_ids': [document_id], 'destination_country': 'RU', 'language': 'zh-CN'})
        results['start_review'] = review.status_code
        check(fields.status_code in (404, 405) and review.status_code == 404)
        check((await c.get('/api/v1/audit/logs')).status_code == 403)
        results['audit_reviewer'] = 403
        check((await c.get('/api/v1/system/models')).status_code == 200)
        results['models'] = 200
        response = await c.post('/api/v1/auth/refresh')
        check(response.status_code == 200)
        c.headers['X-CSRF-Token'] = c.cookies['csrf_token']
        check((await c.post('/api/v1/auth/logout')).status_code == 204)
        check((await c.get('/api/v1/auth/me')).status_code == 401)
        results['refresh_logout'] = '200 refresh; rotated CSRF; 204 logout; me 401 afterwards'
    print(json.dumps(results, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    asyncio.run(main())
