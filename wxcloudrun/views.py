import json
from datetime import datetime
from urllib import error as urllib_error, request as urllib_request

from flask import Response, jsonify, render_template, request
from run import app
from wxcloudrun.dao import delete_counterbyid, query_counterbyid, insert_counter, update_counterbyid
from wxcloudrun.model import Counters
from wxcloudrun.response import make_succ_empty_response, make_succ_response, make_err_response


WECHAT_CUSTOM_SEND_URL = 'http://api.weixin.qq.com/cgi-bin/message/custom/send'
WECHAT_WELCOME_MESSAGE = '天气机器人已连接。'


def _safe_log_value(value, max_length=1000):
    if value is None:
        return None
    text = str(value).replace('\r', '\\r').replace('\n', '\\n')
    return text if len(text) <= max_length else '{}...'.format(text[:max_length])


def _log_wechat_response(status_code, response_body):
    app.logger.info(
        'wechat custom message response status=%s body=%s',
        status_code,
        _safe_log_value(response_body)
    )

    try:
        response_data = json.loads(response_body)
    except (TypeError, ValueError):
        return

    if not isinstance(response_data, dict):
        return

    errcode = response_data.get('errcode')
    errmsg = response_data.get('errmsg')
    if errcode not in (None, 0):
        app.logger.error(
            'wechat custom message response errcode=%s errmsg=%s',
            _safe_log_value(errcode),
            _safe_log_value(errmsg)
        )
    elif errcode is not None or errmsg is not None:
        app.logger.info(
            'wechat custom message response errcode=%s errmsg=%s',
            _safe_log_value(errcode),
            _safe_log_value(errmsg)
        )


@app.route('/health')
def health():
    """
    :return: 服务健康状态
    """
    return jsonify({
        "status": "ok",
        "service": "wechat-weather"
    })


@app.route('/')
def index():
    """
    :return: 返回index页面
    """
    return render_template('index.html')


@app.route('/', methods=['POST'])
def receive_wechat_message():
    """
    :return: 微信云托管消息推送处理结果
    """
    source = request.headers.get('x-wx-source')
    openid = request.headers.get('x-wx-openid')

    if not source:
        return Response('Invalid request source', status=400, mimetype='text/plain')
    if not openid:
        return Response('Missing OpenID', status=400, mimetype='text/plain')

    message_body = request.get_json(silent=True)
    raw_body = request.get_data(as_text=True)
    if isinstance(message_body, dict):
        message_type = message_body.get('MsgType', message_body.get('msgtype'))
        message_content = message_body.get('Content', message_body.get('content'))
    else:
        message_type = None
        message_content = raw_body

    app.logger.info(
        'wechat message received source=%s openid_received=%s message_type=%s message_content=%s',
        _safe_log_value(source),
        bool(openid),
        _safe_log_value(message_type),
        _safe_log_value(message_content)
    )

    payload = json.dumps({
        'touser': openid,
        'msgtype': 'text',
        'text': {
            'content': WECHAT_WELCOME_MESSAGE
        }
    }, ensure_ascii=False).encode('utf-8')
    wechat_request = urllib_request.Request(
        WECHAT_CUSTOM_SEND_URL,
        data=payload,
        headers={'Content-Type': 'application/json'},
        method='POST'
    )

    try:
        with urllib_request.urlopen(wechat_request, timeout=10) as wechat_response:
            response_status = wechat_response.getcode()
            response_body = wechat_response.read().decode('utf-8', errors='replace')
    except urllib_error.HTTPError as exc:
        response_body = exc.read().decode('utf-8', errors='replace')
        _log_wechat_response(exc.code, response_body)
        app.logger.error('wechat custom message request failed with HTTP status=%s', exc.code)
        return Response('WeChat API request failed', status=502, mimetype='text/plain')
    except urllib_error.URLError as exc:
        app.logger.error('wechat custom message request failed reason=%s', _safe_log_value(exc.reason))
        return Response('WeChat API request failed', status=502, mimetype='text/plain')

    _log_wechat_response(response_status, response_body)
    return Response('success', mimetype='text/plain')


@app.route('/api/count', methods=['POST'])
def count():
    """
    :return:计数结果/清除结果
    """

    # 获取请求体参数
    params = request.get_json()

    # 检查action参数
    if 'action' not in params:
        return make_err_response('缺少action参数')

    # 按照不同的action的值，进行不同的操作
    action = params['action']

    # 执行自增操作
    if action == 'inc':
        counter = query_counterbyid(1)
        if counter is None:
            counter = Counters()
            counter.id = 1
            counter.count = 1
            counter.created_at = datetime.now()
            counter.updated_at = datetime.now()
            insert_counter(counter)
        else:
            counter.id = 1
            counter.count += 1
            counter.updated_at = datetime.now()
            update_counterbyid(counter)
        return make_succ_response(counter.count)

    # 执行清0操作
    elif action == 'clear':
        delete_counterbyid(1)
        return make_succ_empty_response()

    # action参数错误
    else:
        return make_err_response('action参数错误')


@app.route('/api/count', methods=['GET'])
def get_count():
    """
    :return: 计数的值
    """
    counter = Counters.query.filter(Counters.id == 1).first()
    return make_succ_response(0) if counter is None else make_succ_response(counter.count)
