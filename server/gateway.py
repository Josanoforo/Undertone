"""Loopback viewer gateway. TLS and backend authority are separate prerequisites."""
import http.client
import os
import re
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

MAX_BODY = 1024 * 1024
MAX_RESPONSE = 20 * 1024 * 1024
TIMEOUT = 130
IDENT = r'[A-Za-z0-9_-]+'
REQUEST = r'[A-Za-z0-9._:-]{1,128}'


def config():
    origin = os.environ.get('APP_PUBLIC_ORIGIN', '')
    secret = os.environ.get('APP_GATEWAY_SECRET', '')
    try:
        u = urlsplit(origin)
        port = u.port
        valid = (u.scheme == 'https' and u.hostname and u.netloc == u.netloc.lower()
                 and not u.username and not u.password and not u.path and not u.query and not u.fragment
                 and not origin.endswith(':443') and u.hostname.isascii()
                 and re.fullmatch(r'[a-z0-9.-]+', u.hostname))
        gp = int(os.environ.get('APP_GATEWAY_PORT', '18876'))
        bp = int(os.environ.get('APP_PORT', '8765'))
        if not valid or len(secret) < 32 or not secret.isascii() or not re.fullmatch(r'[A-Za-z0-9_-]+', secret):
            raise ValueError()
        if not 1 <= gp <= 65535 or not 1 <= bp <= 65535 or gp == bp:
            raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('Invalid gateway configuration') from None
    return origin, u.netloc, secret, gp, bp


def allowed(method, path):
    if method == 'GET' and (path in ('/', '/index.html') or re.fullmatch(r'/assets/[A-Za-z0-9._/-]+', path) and '..' not in path):
        return True
    if method == 'GET' and (re.fullmatch(r'/api/public/(?:activities/)?' + IDENT, path) or re.fullmatch(r'/(?:api/)?p10/public/' + IDENT + '/' + IDENT, path)):
        return True
    prefix = r'/api/sessions/' + IDENT
    if method == 'GET' and re.fullmatch(prefix + r'/identity', path):
        return True
    if method == 'POST' and re.fullmatch(prefix + r'/notebook/import', path):
        return True
    if method == 'GET' and re.fullmatch(prefix + r'/notebook/receipts/' + REQUEST, path):
        return True
    patterns = {
        'GET': [prefix + r'/w13/questions', prefix, prefix + r'/(?:sources|connection|capture-status|bookmarks|conversations|shares)', prefix + r'/conversations/' + IDENT, prefix + r'/p10/timeline', prefix + r'/p12/(?:capabilities|preferences|caption-feed|operations|recaps/' + IDENT + r'|collaboration/routes|collaboration/references)' , prefix + r'/p12/collaboration/(?:routes|references)/' + IDENT, prefix + r'/p12/collaboration/receipts/' + REQUEST, prefix + r'/p12/operations/' + REQUEST + r'(?:/audio)?', prefix + r'/p12/sources/' + IDENT + r'/original-audio', prefix + r'/activities/' + IDENT + r'(?:/contributions)?', prefix + r'/activities/' + IDENT + r'/contributions/' + IDENT + r'/history'],
        'POST': [prefix + r'/w13/questions', prefix + r'/(?:join|bookmarks|attempt-comparison|conversations|shares)', prefix + r'/conversations/' + IDENT + r'/(?:messages|attempts)', prefix + r'/p12/(?:preferences|translations|speech|contribution-grants|collaboration-grants|collaboration/references)', prefix + r'/p12/collaboration-grants/' + IDENT + r'/(?:revoke|withdraw-attribution)', prefix + r'/p12/collaboration/routes/' + IDENT + r'/admit', prefix + r'/p12/contribution-grants/' + IDENT + r'/revoke', prefix + r'/p12/operations/' + REQUEST + r'/cancel', prefix + r'/activities/' + IDENT + r'/(?:participants|contributions)', prefix + r'/activities/' + IDENT + r'/contributions/' + IDENT + r'/(?:withdraw|correct)'],
        'PATCH': [prefix + r'/w13/questions/' + IDENT, prefix + r'/shares/' + IDENT],
        'DELETE': [prefix + r'/w13/questions/' + IDENT, prefix + r'/(?:private-data|bookmarks/' + IDENT + r'|conversations/' + IDENT + r'|shares/' + IDENT + r')'],
    }
    # Backend limits returned answers to the current question author.
    if method == 'GET' and re.fullmatch(prefix + r'/w19/inbox/answers', path):
        return True
    # Backend enforces the viewer credential and current practice rights.
    practice = prefix + r'/w20/practice'
    if method == 'GET' and re.fullmatch(practice + r'/(?:discovery|continuations(?:/' + IDENT + r')?)', path):
        return True
    if method == 'POST' and re.fullmatch(practice + r'/(?:prior-attempts|receipt|continuations(?:/' + IDENT + r'/(?:attempts(?:/' + IDENT + r'/review)?|shares(?:/' + IDENT + r'/revoke)?))?)', path):
        return True
    if method == 'POST' and re.fullmatch(prefix + r'/w23/moments/(?:search|destination|image|audio)', path):
        return True
    # Run ownership, source authority and the final response fence remain in
    # the speech handler; do not expose creator pronunciation-rule routes.
    speech_run = prefix + r'/w21/speech/runs'
    if method == 'POST' and re.fullmatch(speech_run + r'(?:/' + IDENT + r'/(?:chunks|preview|revise|finalize|generation))?', path):
        return True
    if method == 'GET' and re.fullmatch(speech_run + r'/' + IDENT + r'(?:/generation/' + REQUEST + r')?', path):
        return True
    if method == 'DELETE' and re.fullmatch(speech_run + r'/' + IDENT + r'/generation/' + REQUEST, path):
        return True
    # Delivery remains authorized by the backend for each current subscriber;
    # expose only the source projection and the exact ticket operations.
    if method == 'GET' and re.fullmatch(prefix + r'/w20/delivery-sources', path):
        return True
    if method == 'POST' and re.fullmatch(prefix + r'/w20/delivery(?:/receipt)?', path):
        return True
    if method in ('GET', 'DELETE') and re.fullmatch(prefix + r'/w20/delivery/[0-9a-f]{64}', path):
        return True
    if method == 'GET' and re.fullmatch(prefix + r'/w24/packs/' + IDENT, path):
        return True
    # Visual association reads require the viewer's own current source and receipt rights.
    if method == 'GET' and re.fullmatch(prefix + r'/w26/visual-associations/' + IDENT, path):
        return True
    # Meaning flags and source inspection remain private to the current viewer.
    meaning = prefix + r'/w26/meaning'
    if method == 'POST' and re.fullmatch(meaning + r'/(?:inspect|flags)', path):
        return True
    if method in ('GET', 'PATCH') and re.fullmatch(meaning + r'/flags/' + IDENT, path):
        return True
    # Trail and approved export recheck actor and source rights in the backend.
    if method == 'POST' and re.fullmatch(prefix + r'/w27/(?:moments/trail|export)', path):
        return True
    # Coedit handoff metadata remains subject to current backend draft rights.
    handoff = prefix + r'/w28/handoffs/' + IDENT
    if method == 'GET' and re.fullmatch(handoff + r'(?:/receipts/' + REQUEST + r')?', path):
        return True
    if method == 'POST' and re.fullmatch(handoff + r'/(?:offer|decide)', path):
        return True
    # Private listening preferences are authenticated and fenced by the backend.
    if method in ('GET', 'PUT') and re.fullmatch(prefix + r'/w25/listening/preferences', path):
        return True
    # The archive profile is actor-private; the backend rechecks the current
    # viewer credential, selected source and both archive grants on each call.
    if method == 'PUT' and re.fullmatch(prefix + r'/w24/packs/profile-selection', path):
        return True
    if method == 'GET' and re.fullmatch(prefix + r'/w24/packs/profile-selection-receipts/' + REQUEST, path):
        return True
    if method == 'POST' and re.fullmatch(prefix + r'/w24/packs/profile-generation', path):
        return True
    if method == 'GET' and re.fullmatch(prefix + r'/w24/packs/profile-generation/' + IDENT + r'/' + REQUEST, path):
        return True
    if method == 'GET' and re.fullmatch(prefix + r'/w23/speech/(?:profiles|selection|operations/' + REQUEST + r'|generation/' + IDENT + r'/' + REQUEST + r')', path):
        return True
    if method == 'PUT' and re.fullmatch(prefix + r'/w23/speech/selection', path):
        return True
    if method == 'POST' and re.fullmatch(prefix + r'/w23/speech/generation/prepare', path):
        return True
    if method == 'GET' and re.fullmatch(prefix + r'/w24/activity/activities/' + IDENT + r'(?:/versions/[0-9]+)?', path):
        return True
    if method == 'POST' and re.fullmatch(prefix + r'/w24/activity/(?:activity-reasons(?:/withdraw)?|activities/' + IDENT + r'/demonstrate)', path):
        return True
    return any(re.fullmatch(p, path) for p in patterns.get(method, ()))


class Gateway(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, settings):
        self.settings = settings
        super().__init__(address, Handler)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'Companion'
    sys_version = ''
    def setup(self):
        super().setup()
        self.connection.settimeout(15)
    def log_message(self, *args):
        pass
    def fail(self, status):
        self.close_connection = True
        body = b'{"error":{"code":"gateway_denied","message":"Request unavailable."}}'
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def do_GET(self): self.proxy()
    def do_POST(self): self.proxy()
    def do_PUT(self): self.proxy()
    def do_PATCH(self): self.proxy()
    def do_DELETE(self): self.proxy()
    def do_OPTIONS(self): self.fail(403)
    def proxy(self):
        origin, host, secret, _, backend_port = self.server.settings
        names = [k.lower() for k, _ in self.headers.raw_items()]
        forbidden = ('forwarded', 'via', 'x-forwarded', 'x-real-ip', 'x-companion-gateway', 'proxy-authorization', 'x-activity-owner')
        if (any(n in forbidden or n.startswith('x-forwarded-') for n in names)
            or any(names.count(n) > 1 for n in ('host', 'origin', 'content-length', 'authorization', 'content-type', 'x-activity-participant'))
            or (self.headers.get('X-Activity-Participant') is not None and not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', self.headers.get('X-Activity-Participant')))
            or 'transfer-encoding' in names or 'expect' in names
            or self.headers.get('Host') != host
            or (self.headers.get('Origin') is not None and self.headers.get('Origin') != origin)
            or (self.command != 'GET' and self.headers.get('Origin') != origin)
            or self.headers.get('Sec-Fetch-Site', '') == 'cross-site'
            or (self.command != 'GET' and self.headers.get('Sec-Fetch-Site', '') == 'none')):
            return self.fail(403)
        target = urlsplit(self.path)
        if target.scheme or target.netloc or '%' in target.path or not allowed(self.command, target.path):
            return self.fail(404)
        try:
            length_text = self.headers.get('Content-Length', '0')
            if not re.fullmatch(r'[0-9]+', length_text): return self.fail(400)
            length = int(length_text)
            if length > MAX_BODY: return self.fail(413)
            if self.command == 'GET' and length: return self.fail(400)
            body = self.rfile.read(length)
            if len(body) != length: return self.fail(400)
            headers = {'Host': host, 'X-Companion-Gateway': secret, 'Connection': 'close'}
            for name in ('Origin', 'Authorization', 'Content-Type', 'Sec-Fetch-Site', 'X-Activity-Participant'):
                if self.headers.get(name) is not None: headers[name] = self.headers[name]
            conn = http.client.HTTPConnection('127.0.0.1', backend_port, timeout=TIMEOUT)
            try:
                conn.request(self.command, self.path, body=body if length else None, headers=headers)
                response = conn.getresponse()
                data = response.read(MAX_RESPONSE + 1)
                if len(data) > MAX_RESPONSE: return self.fail(502)
                self.send_response(response.status)
                for name in ('Content-Type', 'Content-Security-Policy', 'X-Content-Type-Options', 'X-Capture-Time-Provenance', 'X-Received-At'):
                    value = response.getheader(name)
                    if value: self.send_header(name, value)
                participant=response.getheader('X-Activity-Participant')
                if participant and self.command=='POST' and re.fullmatch(r'/api/sessions/' + IDENT + r'/activities/' + IDENT + r'/participants',target.path) and response.status<400 and re.fullmatch(r'[A-Za-z0-9_-]{32,128}',participant):self.send_header('X-Activity-Participant',participant)
                self.send_header('Cache-Control', 'no-store')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            finally:
                conn.close()
        except (OSError, http.client.HTTPException, ValueError):
            try: self.fail(502)
            except OSError: pass


def main():
    try:
        settings = config()
        with Gateway(('127.0.0.1', settings[3]), settings) as server:
            print('Gateway listening on loopback; HTTPS ingress and backend enforcement are required.', flush=True)
            server.serve_forever()
    except (ValueError, OSError):
        raise SystemExit('Gateway configuration or listener unavailable.') from None


if __name__ == '__main__':
    main()
