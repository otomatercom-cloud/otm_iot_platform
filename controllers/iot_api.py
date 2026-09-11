# -*- coding: utf-8 -*-
import json

from odoo import fields, http
from odoo.http import request


def _json_response(payload, status=200):
    return request.make_response(
        json.dumps(payload),
        headers=[('Content-Type', 'application/json')],
        status=status,
    )


def _get_json_body():
    try:
        return json.loads(request.httprequest.data or b'{}')
    except (ValueError, TypeError):
        return {}


def _safe_int(value):
    """Never trust a browser/bridge-supplied id's type before browse() (see ERP tooling
    finding #20 - <select>/JS always sends ids as strings)."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return False


class IotBridgeController(http.Controller):
    """Endpoints called by the external MQTT/Tuya bridge service (not an Odoo user session).
    Note: uses type='http' (not 'json'/'jsonrpc') so the bridge can POST plain JSON without
    speaking Odoo's JSON-RPC envelope - same pattern as the existing Telegram/WhatsApp webhooks.
    Authenticated per-device via the device's own secret token in the JSON body."""

    @http.route('/api/iot/device/state', type='http', auth='public', methods=['POST'], csrf=False)
    def device_state(self, **kwargs):
        payload = _get_json_body()
        external_id = payload.get('external_id')
        secret = payload.get('device_secret')
        device = request.env['otm.iot.device'].sudo().search([('external_id', '=', external_id)], limit=1)
        if not device or not secret or device.device_secret != secret:
            return _json_response({'error': 'unauthorized'}, status=401)

        channel_no = _safe_int(payload.get('channel_no'))
        is_on = bool(payload.get('is_on'))
        now = fields.Datetime.now()

        device.sudo().write({'status': 'online', 'last_seen': now})

        if channel_no:
            channel = device.channel_ids.filtered(lambda c: c.channel_no == channel_no)
            if channel and channel.is_on != is_on:
                channel.sudo().write({'is_on': is_on, 'last_changed': now})
                request.env['otm.iot.device.log'].sudo().create({
                    'device_id': device.id,
                    'channel_no': channel_no,
                    'event_type': 'on' if is_on else 'off',
                    'timestamp': now,
                })
        return _json_response({'ok': True})

    @http.route('/api/iot/bridge/commands/pending', type='http', auth='public', methods=['POST'], csrf=False)
    def pending_commands(self, **kwargs):
        payload = _get_json_body()
        bridge_key = payload.get('bridge_key')
        expected = request.env['ir.config_parameter'].sudo().get_param('otm_iot_platform.bridge_key')
        if not expected or bridge_key != expected:
            return _json_response({'error': 'unauthorized'}, status=401)

        protocol = payload.get('protocol')  # 'mqtt' or 'tuya' - bridge asks for its own slice
        domain = [('state', '=', 'pending')]
        commands = request.env['otm.iot.device.command'].sudo().search(domain, limit=200)
        if protocol:
            commands = commands.filtered(lambda c: c.device_id.protocol == protocol)

        result = [{
            'command_id': c.id,
            'external_id': c.device_id.external_id,
            'protocol': c.device_id.protocol,
            'mqtt_topic_command': c.device_id.mqtt_topic_command,
            'tuya_device_id': c.device_id.external_id if c.device_id.protocol == 'tuya' else False,
            'channel_no': c.channel_no,
            'command': c.command,
        } for c in commands]
        commands.action_mark_sent()
        return _json_response({'commands': result})

    @http.route('/api/iot/bridge/commands/ack', type='http', auth='public', methods=['POST'], csrf=False)
    def ack_command(self, **kwargs):
        payload = _get_json_body()
        bridge_key = payload.get('bridge_key')
        expected = request.env['ir.config_parameter'].sudo().get_param('otm_iot_platform.bridge_key')
        if not expected or bridge_key != expected:
            return _json_response({'error': 'unauthorized'}, status=401)

        command_id = _safe_int(payload.get('command_id'))
        command = request.env['otm.iot.device.command'].sudo().browse(command_id)
        if not command.exists():
            return _json_response({'error': 'not_found'}, status=404)

        if payload.get('success'):
            command.action_mark_acked()
        else:
            command.action_mark_failed(payload.get('error_message'))
        return _json_response({'ok': True})


class IotCustomerController(http.Controller):
    """Endpoints called by the customer-facing app (Next.js PWA), authenticated as a logged-in
    Odoo user (portal or internal) via normal session auth (cookie set at login)."""

    @http.route('/api/iot/devices', type='http', auth='user', methods=['GET'], csrf=False)
    def list_devices(self, **kwargs):
        partner = request.env.user.partner_id
        devices = request.env['otm.iot.device'].search([('partner_id', '=', partner.id)])
        return _json_response({
            'subscription_active': partner.iot_subscription_active,
            'subscription_valid_until': str(partner.iot_subscription_valid_until or ''),
            'devices': [{
                'id': d.id,
                'name': d.name,
                'type': d.device_type_id.name,
                'icon': d.device_type_id.icon,
                'location': d.location,
                'status': d.status,
                'last_seen': str(d.last_seen or ''),
                'channels': [{
                    'channel_no': c.channel_no,
                    'name': c.name,
                    'is_on': c.is_on,
                } for c in d.channel_ids],
            } for d in devices],
        })

    @http.route('/api/iot/device/toggle', type='http', auth='user', methods=['POST'], csrf=False)
    def toggle_channel(self, **kwargs):
        payload = _get_json_body()
        partner = request.env.user.partner_id
        device_id = _safe_int(payload.get('device_id'))
        channel_no = _safe_int(payload.get('channel_no'))

        device = request.env['otm.iot.device'].search([
            ('id', '=', device_id), ('partner_id', '=', partner.id),
        ], limit=1)
        if not device:
            return _json_response({'error': 'device_not_found_or_not_yours'}, status=404)
        if not partner.iot_subscription_active:
            return _json_response({'error': 'subscription_inactive'}, status=403)

        channel = device.channel_ids.filtered(lambda c: c.channel_no == channel_no)
        if not channel:
            return _json_response({'error': 'channel_not_found'}, status=404)

        channel.action_toggle()
        return _json_response({'ok': True, 'queued': True})
