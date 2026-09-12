# -*- coding: utf-8 -*-
import secrets

from odoo import api, fields, models
from odoo.exceptions import ValidationError


class IotDevice(models.Model):
    _name = 'otm.iot.device'
    _description = 'IoT Device'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(string='Device Name', required=True, tracking=True)
    device_type_id = fields.Many2one('otm.iot.device.type', string='Device Type', required=True, tracking=True)
    protocol = fields.Selection(related='device_type_id.protocol', store=True, readonly=True)

    # Not required: a device can sit in stock, unclaimed, before any customer owns it.
    # Assigned either by an admin directly, or by a customer claiming it via claim_code.
    partner_id = fields.Many2one('res.partner', string='Customer', index=True, tracking=True)
    is_claimed = fields.Boolean(string='Claimed', compute='_compute_is_claimed', store=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    external_id = fields.Char(
        string='External Device ID',
        help='MAC address (MQTT devices) or Tuya device_id (Tuya devices). Must be unique.',
        required=True, index=True,
    )
    device_secret = fields.Char(string='Device Secret', copy=False, help='Auth token used by the bridge when posting state for this device')
    claim_code = fields.Char(
        string='Claim Code', copy=False, index=True,
        help='Short code you give the customer (e.g. printed on the device or its box) so they can '
             'connect it to their account from the app after subscribing. Not the same as the device secret.',
    )

    mqtt_topic_state = fields.Char(string='MQTT State Topic', help='e.g. otm/iot/<external_id>/state')
    mqtt_topic_command = fields.Char(string='MQTT Command Topic', help='e.g. otm/iot/<external_id>/cmd')

    room_id = fields.Many2one('otm.iot.room', string='Room', index=True,
                               help='Structured room assignment. When set, "Location" below is kept in sync automatically.')
    location = fields.Char(string='Location / Room', help='Free-text fallback shown when no structured Room is assigned.')
    status = fields.Selection([
        ('online', 'Online'),
        ('offline', 'Offline'),
    ], string='Connectivity', default='offline', tracking=True)
    last_seen = fields.Datetime(string='Last Seen')

    channel_ids = fields.One2many('otm.iot.device.channel', 'device_id', string='Channels')
    channel_count_display = fields.Integer(related='device_type_id.channel_count', string='Channel Count')
    command_ids = fields.One2many('otm.iot.device.command', 'device_id', string='Commands')
    log_ids = fields.One2many('otm.iot.device.log', 'device_id', string='Event Log')

    active = fields.Boolean(default=True)

    _external_id_uniq = models.Constraint('unique(external_id)', 'A device with this External Device ID is already registered.')
    _claim_code_uniq = models.Constraint('unique(claim_code)', 'A device with this Claim Code already exists.')

    @api.depends('partner_id')
    def _compute_is_claimed(self):
        for record in self:
            record.is_claimed = bool(record.partner_id)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('device_secret'):
                vals['device_secret'] = secrets.token_hex(16)
            if not vals.get('claim_code'):
                vals['claim_code'] = secrets.token_hex(4).upper()
            if not vals.get('mqtt_topic_state') and vals.get('external_id'):
                vals['mqtt_topic_state'] = 'otm/iot/%s/state' % vals['external_id']
            if not vals.get('mqtt_topic_command') and vals.get('external_id'):
                vals['mqtt_topic_command'] = 'otm/iot/%s/cmd' % vals['external_id']
            if vals.get('room_id') and not vals.get('location'):
                room = self.env['otm.iot.room'].browse(vals['room_id'])
                vals['location'] = room.name
        records = super().create(vals_list)
        for record in records:
            # Only enforce the subscription/device-limit check when a customer is assigned
            # up front (admin manually assigning). Unclaimed stock skips it entirely -
            # the check runs again at claim time in claim_device() below.
            if record.partner_id:
                record._check_subscription_device_limit()
            if not record.channel_ids:
                record._generate_channels()
        return records

    def write(self, vals):
        if vals.get('room_id'):
            room = self.env['otm.iot.room'].browse(vals['room_id'])
            vals.setdefault('location', room.name)
        result = super().write(vals)
        if vals.get('partner_id'):
            for record in self:
                record._check_subscription_device_limit()
        return result

    def _generate_channels(self):
        Channel = self.env['otm.iot.device.channel']
        for record in self:
            existing = len(record.channel_ids)
            wanted = record.device_type_id.channel_count or 1
            for i in range(existing + 1, wanted + 1):
                Channel.create({
                    'device_id': record.id,
                    'channel_no': i,
                    'name': 'Channel %s' % i,
                })

    def _check_subscription_device_limit(self):
        for record in self:
            partner = record.partner_id
            if not partner:
                continue
            if not partner.iot_subscription_active:
                raise ValidationError(
                    "%s has no active IoT subscription. Activate a subscription plan before registering devices." % partner.display_name
                )
            if partner.iot_max_devices and partner.iot_device_count > partner.iot_max_devices:
                raise ValidationError(
                    "%s's subscription plan allows a maximum of %s device(s). Upgrade the plan to add more devices."
                    % (partner.display_name, partner.iot_max_devices)
                )

    def action_regenerate_secret(self):
        for record in self:
            record.device_secret = secrets.token_hex(16)

    def action_regenerate_claim_code(self):
        for record in self:
            record.claim_code = secrets.token_hex(4).upper()

    def assign_room(self, room):
        """Move this device into a room. room must belong to the same customer as the device -
        prevents a customer from ever pointing their device at someone else's room."""
        self.ensure_one()
        if room and room.partner_id != self.partner_id:
            return False, 'room_not_yours'
        self.write({'room_id': room.id if room else False})
        return self, False

    def action_send_command(self, channel_no, command):
        """Queue a switch command for the bridge service to deliver (MQTT publish or Tuya API call)."""
        self.ensure_one()
        return self.env['otm.iot.device.command'].create({
            'device_id': self.id,
            'channel_no': channel_no,
            'command': command,
            'state': 'pending',
        })

    @api.model
    def claim_device(self, claim_code, partner):
        """Called (via sudo, from the customer-app controller) when a customer enters a claim
        code in the app. Only matches devices that are still unclaimed (partner_id is False).
        Returns (device, error_code) - error_code is False on success."""
        claim_code = (claim_code or '').strip().upper()
        if not claim_code:
            return False, 'claim_code_required'

        device = self.search([('claim_code', '=', claim_code), ('partner_id', '=', False)], limit=1)
        if not device:
            return False, 'invalid_or_already_claimed'

        if not partner.iot_subscription_active:
            return False, 'no_active_subscription'
        if partner.iot_max_devices and partner.iot_device_count >= partner.iot_max_devices:
            return False, 'device_limit_reached'

        device.write({'partner_id': partner.id})
        if not device.channel_ids:
            device._generate_channels()
        return device, False
