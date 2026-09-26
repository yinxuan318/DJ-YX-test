import json
import unittest
from unittest.mock import patch

from wxcloudrun import app
from wxcloudrun.views import WECHAT_CUSTOM_SEND_URL, WECHAT_WELCOME_MESSAGE


class FakeWeChatResponse:
    def __init__(self, status_code=200, body=b'{"errcode":0,"errmsg":"ok"}'):
        self.status_code = status_code
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def getcode(self):
        return self.status_code

    def read(self):
        return self.body


class MessageHandlerTestCase(unittest.TestCase):
    def setUp(self):
        app.config['TESTING'] = True
        self.client = app.test_client()

    def test_health_route_remains_available(self):
        response = self.client.get('/health')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {
            'status': 'ok',
            'service': 'wechat-weather'
        })

    def test_index_route_remains_available(self):
        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)

    def test_post_requires_wx_source(self):
        response = self.client.post('/', headers={'x-wx-openid': 'openid-test'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_data(as_text=True), 'Invalid request source')

    def test_post_requires_openid(self):
        response = self.client.post('/', headers={'x-wx-source': 'wechat'})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_data(as_text=True), 'Missing OpenID')

    def test_post_accepts_message_push_configuration_check(self):
        response = self.client.post(
            '/',
            headers={'x-wx-source': 'wechat'},
            json={'action': 'CheckContainerPath'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), 'success')

    @patch('wxcloudrun.views.urllib_request.urlopen')
    def test_post_sends_cloud_call_and_returns_success(self, mock_urlopen):
        mock_urlopen.return_value = FakeWeChatResponse()

        response = self.client.post(
            '/',
            headers={
                'x-wx-source': 'wechat',
                'x-wx-openid': 'openid-test'
            },
            json={
                'MsgType': 'text',
                'Content': 'hello'
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), 'success')
        mock_urlopen.assert_called_once()

        cloud_call = mock_urlopen.call_args.args[0]
        self.assertEqual(cloud_call.full_url, WECHAT_CUSTOM_SEND_URL)
        self.assertEqual(cloud_call.get_method(), 'POST')
        self.assertEqual(
            json.loads(cloud_call.data.decode('utf-8')),
            {
                'touser': 'openid-test',
                'msgtype': 'text',
                'text': {
                    'content': WECHAT_WELCOME_MESSAGE
                }
            }
        )

    @patch('wxcloudrun.views.urllib_request.urlopen')
    def test_post_accepts_non_json_body(self, mock_urlopen):
        mock_urlopen.return_value = FakeWeChatResponse()

        response = self.client.post(
            '/',
            headers={
                'x-wx-source': 'wechat',
                'x-wx-openid': 'openid-test'
            },
            data='<xml><MsgType>text</MsgType></xml>',
            content_type='application/xml'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_data(as_text=True), 'success')
        mock_urlopen.assert_called_once()


if __name__ == '__main__':
    unittest.main()
