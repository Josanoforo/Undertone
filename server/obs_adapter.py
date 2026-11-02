"""Bounded OBS WebSocket 5 client for the owned local OBS fixture.

This module is transport only. Callers must enforce durable receipts, material
rights and fail-closed reconciliation before using any mutating request.
"""
import base64
import hashlib
import json
import os
import socket
import struct
import uuid

_MAX_MESSAGE = 8 * 1024 * 1024
_ALLOWED = frozenset({'GetVersion', 'GetSceneList', 'GetInputList', 'GetProfileList',
                      'GetSceneCollectionList', 'GetStreamStatus', 'GetRecordStatus',
                      'GetVirtualCamStatus', 'GetCurrentProgramScene', 'GetSceneItemList',
                      'GetSceneItemEnabled', 'GetSourceScreenshot', 'CreateScene', 'SetCurrentProgramScene',
                      'SetSceneItemEnabled', 'SetInputSettings', 'CreateInput', 'GetInputKindList', 'GetInputSettings'})

class OBSError(Exception):
    pass

class OBSClient:
    def __init__(self, port, password, timeout=5):
        if type(port) is not int or not 1 <= port <= 65535 or not isinstance(password, str) or not password:
            raise ValueError('Valid local port and password required')
        self.port, self.password, self.timeout = port, password, timeout
        self.sock = None
        self.buffer = b''

    def __enter__(self):
        try:
            self.sock = socket.create_connection(('127.0.0.1', self.port), self.timeout)
            nonce = base64.b64encode(os.urandom(16)).decode('ascii')
            request = ('GET / HTTP/1.1\r\nHost: 127.0.0.1:%d\r\nUpgrade: websocket\r\n'
                       'Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n'
                       'Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: obswebsocket.json\r\n\r\n') % (self.port, nonce)
            self.sock.sendall(request.encode('ascii'))
            while b'\r\n\r\n' not in self.buffer:
                self.buffer += self._recv()
                if len(self.buffer) > 16384: raise OBSError('Invalid handshake')
            raw, self.buffer = self.buffer.split(b'\r\n\r\n', 1)
            lines = raw.decode('ascii').split('\r\n')
            headers = {}
            for line in lines[1:]:
                k, v = line.split(':', 1); headers[k.strip().lower()] = v.strip()
            accept = base64.b64encode(hashlib.sha1((nonce+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()).decode('ascii')
            if not lines[0].startswith('HTTP/1.1 101 ') or headers.get('sec-websocket-accept') != accept or headers.get('sec-websocket-protocol') != 'obswebsocket.json':
                raise OBSError('WebSocket handshake rejected')
            hello = self._message()
            if hello.get('op') != 0 or not isinstance(hello.get('d', {}).get('authentication'), dict):
                raise OBSError('Authenticated OBS endpoint required')
            auth = hello['d']['authentication']
            secret = base64.b64encode(hashlib.sha256((self.password + auth['salt']).encode()).digest()).decode('ascii')
            response = base64.b64encode(hashlib.sha256((secret + auth['challenge']).encode()).digest()).decode('ascii')
            self._send({'op': 1, 'd': {'rpcVersion': 1, 'authentication': response, 'eventSubscriptions': 0}})
            if self._message().get('op') != 2: raise OBSError('OBS authentication failed')
            return self
        except Exception:
            self.close()
            raise

    def __exit__(self, *args): self.close()
    def close(self):
        if self.sock:
            self.sock.close(); self.sock = None
    def _recv(self):
        data = self.sock.recv(65536)
        if not data: raise OBSError('OBS connection closed; operation outcome may be unknown')
        return data
    def _take(self, count):
        while len(self.buffer) < count: self.buffer += self._recv()
        result, self.buffer = self.buffer[:count], self.buffer[count:]
        return result
    def _frame(self, opcode, payload):
        mask = os.urandom(4); n = len(payload)
        if n > _MAX_MESSAGE: raise OBSError('OBS message too large')
        length = bytes([0x80 | n]) if n < 126 else (bytes([0x80 | 126]) + struct.pack('!H', n) if n < 65536 else bytes([0x80 | 127]) + struct.pack('!Q', n))
        self.sock.sendall(bytes([0x80 | opcode]) + length + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
    def _send(self, value): self._frame(1, json.dumps(value, separators=(',', ':')).encode('utf-8'))
    def _message(self):
        while True:
            first, second = self._take(2)
            if not first & 0x80 or first & 0x70 or second & 0x80: raise OBSError('Unsupported OBS frame')
            opcode = first & 15; n = second & 127
            if n == 126: n = struct.unpack('!H', self._take(2))[0]
            elif n == 127: n = struct.unpack('!Q', self._take(8))[0]
            if n > _MAX_MESSAGE: raise OBSError('OBS message too large')
            payload = self._take(n)
            if opcode == 9:
                self._frame(10, payload); continue
            if opcode != 1: raise OBSError('Unexpected OBS frame')
            try: result = json.loads(payload.decode('utf-8'))
            except (UnicodeError, ValueError) as exc: raise OBSError('Invalid OBS response') from exc
            if not isinstance(result, dict): raise OBSError('Invalid OBS response')
            return result
    def request(self, kind, data=None):
        if kind not in _ALLOWED: raise ValueError('OBS request not allowed')
        request_id = uuid.uuid4().hex
        self._send({'op': 6, 'd': {'requestType': kind, 'requestId': request_id, 'requestData': data or {}}})
        while True:
            message = self._message()
            if message.get('op') == 5: continue
            d = message.get('d', {})
            if message.get('op') != 7 or d.get('requestId') != request_id or d.get('requestType') != kind:
                raise OBSError('Unmatched OBS response; operation outcome may be unknown')
            if not d.get('requestStatus', {}).get('result'):
                raise OBSError('OBS rejected request (%s)' % d.get('requestStatus', {}).get('code', 'unknown'))
            return d.get('responseData', {})


def cue_password(config):
    # An operator may reference the existing protected OBS credential instead
    # of copying its password into a second cue configuration file.
    if 'credentialFile' in config:
        if 'password' in config or not isinstance(config['credentialFile'], str):
            raise ValueError('Invalid OBS credential binding')
        with open(config['credentialFile'], encoding='utf-8') as credential_file:
            credential = json.load(credential_file)
        if not isinstance(credential, dict):
            raise ValueError('Invalid OBS credential file')
        if credential.get('server_port') != config['port']:
            raise ValueError('OBS credential port does not match destination')
        password = credential['server_password']
    else:
        password = config['password']
    if not isinstance(password, str) or not password:
        raise ValueError('Invalid OBS credential')
    return password


# Trusted local cue transport. Configuration is supplied by the operator, never
# by an HTTP caller; identity is checked again before each native mutation.
def cue_effect(config, url, action):
    import time
    scene = config['scene']
    name = config['input']
    item = config['itemId']
    password = cue_password(config)
    with OBSClient(config['port'], password, timeout=20) as client:
        program = client.request('GetCurrentProgramScene')
        if program.get('currentProgramSceneName') != scene or program.get('currentProgramSceneUuid') != config['sceneUuid']:
            raise OBSError('Owned Program scene identity changed')
        if client.request('GetProfileList').get('currentProfileName') != config['profile'] or client.request('GetSceneCollectionList').get('currentSceneCollectionName') != config['collection']:
            raise OBSError('Owned OBS profile identity changed')
        if any(client.request(k).get('outputActive') for k in ('GetStreamStatus', 'GetRecordStatus', 'GetVirtualCamStatus')):
            raise OBSError('OBS output is active')
        items = client.request('GetSceneItemList', {'sceneName': scene}).get('sceneItems', [])
        if not any(x.get('sceneItemId') == item and x.get('sourceName') == name for x in items):
            raise OBSError('Owned scene item identity changed')
        settings = client.request('GetInputSettings', {'inputName': name})
        if settings.get('inputKind') != 'browser_source':
            raise OBSError('Owned input kind changed')
        enabled = client.request('GetSceneItemEnabled', {'sceneName': scene, 'sceneItemId': item})['sceneItemEnabled']
        if action == 'present':
            if enabled:
                raise OBSError('Owned input already enabled; reconcile before presenting')
            client.request('SetInputSettings', {'inputName': name, 'inputSettings': {'url': url}, 'overlay': True})
            if client.request('GetInputSettings', {'inputName': name})['inputSettings'].get('url') != url:
                raise OBSError('Owned input URL did not match')
            client.request('SetSceneItemEnabled', {'sceneName': scene, 'sceneItemId': item, 'sceneItemEnabled': True})
            if not client.request('GetSceneItemEnabled', {'sceneName': scene, 'sceneItemId': item})['sceneItemEnabled']:
                raise OBSError('Owned input was not enabled')
            time.sleep(12)
        elif action == 'withdraw':
            if settings['inputSettings'].get('url') != url:
                raise OBSError('Owned input no longer matches cue')
            if enabled:
                client.request('SetSceneItemEnabled', {'sceneName': scene, 'sceneItemId': item, 'sceneItemEnabled': False})
            if client.request('GetSceneItemEnabled', {'sceneName': scene, 'sceneItemId': item})['sceneItemEnabled']:
                raise OBSError('Owned input was not disabled')
            time.sleep(2)
        else:
            raise ValueError('Invalid cue action')
        shot = client.request('GetSourceScreenshot', {'sourceName': scene, 'imageFormat': 'png', 'imageWidth': 1280, 'imageHeight': 720}).get('imageData', '')
        if not shot.startswith('data:image/png;base64,'):
            raise OBSError('Invalid OBS PNG receipt')
        try:
            image = base64.b64decode(shot.split(',', 1)[1], validate=True)
        except ValueError as exc:
            raise OBSError('Invalid OBS PNG receipt') from exc
        if not image.startswith(b'\x89PNG\r\n\x1a\n'):
            raise OBSError('Invalid OBS PNG receipt')
        return {'scene': scene, 'sceneUuid': config['sceneUuid'], 'input': name, 'sceneItemId': item,
                'url': url, 'enabled': action == 'present', 'pngSha256': hashlib.sha256(image).hexdigest(), 'imageData': shot}
