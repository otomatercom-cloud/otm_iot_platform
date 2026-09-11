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

    @http.route('/api/iot/plans', type='http', auth='user', methods=['GET'], csrf=False)
    def list_plans(self, **kwargs):
        plans = request.env['otm.iot.subscription.plan'].search([('active', '=', True)], order='price')
        return _json_response({
            'plans': [{
                'id': p.id,
                'name': p.name,
                'price': p.price,
                'currency': p.currency_id.name,
                'duration_days': p.duration_days,
                'max_devices': p.max_devices,
                'description': p.description or '',
            } for p in plans],
        })

    @http.route('/api/iot/subscribe/confirm', type='http', auth='user', methods=['POST'], csrf=False)
    def confirm_subscription(self, **kwargs):
        """Called by our own Next.js server (never the browser) after it has independently
        verified the Razorpay payment signature. Trust boundary: session auth identifies the
        customer, but the payment itself was already verified server-to-server before this call."""
        payload = _get_json_body()
        partner = request.env.user.partner_id
        plan_id = _safe_int(payload.get('plan_id'))
        payment_reference = payload.get('payment_reference')

        plan = request.env['otm.iot.subscription.plan'].sudo().browse(plan_id)
        if not plan.exists() or not plan.active:
            return _json_response({'error': 'invalid_plan'}, status=400)

        payment = partner.sudo().action_renew_iot_subscription(
            plan_id=plan.id, payment_reference=payment_reference
        )
        if not payment:
            return _json_response({'error': 'renewal_failed'}, status=500)

        return _json_response({
            'ok': True,
            'plan': plan.name,
            'valid_until': str(partner.iot_subscription_valid_until or ''),
        })

    @http.route('/api/iot/bank-details', type='http', auth='user', methods=['GET'], csrf=False)
    def bank_details(self, **kwargs):
        ICP = request.env['ir.config_parameter'].sudo()
        return _json_response({
            'account_name': ICP.get_param('otm_iot_platform.bank_account_name', ''),
            'account_number': ICP.get_param('otm_iot_platform.bank_account_number', ''),
            'ifsc': ICP.get_param('otm_iot_platform.bank_ifsc', ''),
            'bank_name': ICP.get_param('otm_iot_platform.bank_name', ''),
            'upi_id': ICP.get_param('otm_iot_platform.bank_upi_id', ''),
        })

    @http.route('/api/iot/subscribe/bank-transfer', type='http', auth='user', methods=['POST'], csrf=False)
    def submit_bank_transfer(self, **kwargs):
        """Customer declares they've sent a bank transfer. This does NOT activate anything -
        it creates an unverified payment record an admin must approve (see action_verify_payment).
        Testing-mode friendly: no gateway required, just a manual reconciliation step."""
        payload = _get_json_body()
        partner = request.env.user.partner_id
        plan_id = _safe_int(payload.get('plan_id'))
        reference = payload.get('reference')
        note = payload.get('note')

        plan = request.env['otm.iot.subscription.plan'].sudo().browse(plan_id)
        if not plan.exists() or not plan.active:
            return _json_response({'error': 'invalid_plan'}, status=400)
        if not reference:
            return _json_response({'error': 'reference_required'}, status=400)

        payment = request.env['otm.iot.subscription.payment'].sudo().create({
            'partner_id': partner.id,
            'plan_id': plan.id,
            'payment_reference': reference,
            'payment_method': 'bank_transfer',
            'customer_note': note,
        })
        return _json_response({'ok': True, 'status': 'pending_verification', 'payment_id': payment.id})

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
                    'is_favorite': c.is_favorite,
                } for c in d.channel_ids],
            } for d in devices],
        })

    @http.route('/api/iot/devices/bulk-toggle', type='http', auth='user', methods=['POST'], csrf=False)
    def bulk_toggle(self, **kwargs):
        """Powers the 'Start Home' / 'Stop Home' scene buttons: queues on/off commands for
        every favorite channel across all of this customer's devices in one call."""
        payload = _get_json_body()
        partner = request.env.user.partner_id
        turn = payload.get('turn')  # 'on' or 'off'
        if turn not in ('on', 'off'):
            return _json_response({'error': 'turn_must_be_on_or_off'}, status=400)
        if not partner.iot_subscription_active:
            return _json_response({'error': 'subscription_inactive'}, status=403)

        devices = request.env['otm.iot.device'].search([('partner_id', '=', partner.id)])
        queued = 0
        for device in devices:
            channels = device.channel_ids.filtered(lambda c: c.is_favorite)
            for channel in channels:
                if (turn == 'on') == channel.is_on:
                    continue  # already in the target state, nothing to queue
                device.action_send_command(channel.channel_no, turn)
                queued += 1

        return _json_response({'ok': True, 'queued': queued})

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
