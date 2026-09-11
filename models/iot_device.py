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

    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True, tracking=True)
    company_id = fields.Many2one('res.company', string='Company', default=lambda self: self.env.company)

    external_id = fields.Char(
        string='External Device ID',
        help='MAC address (MQTT devices) or Tuya device_id (Tuya devices). Must be unique.',
        required=True, index=True,
    )
    device_secret = fields.Char(string='Device Secret', copy=False, help='Auth token used by the bridge when posting state for this device')

    mqtt_topic_state = fields.Char(string='MQTT State Topic', help='e.g. otm/iot/<external_id>/state')
    mqtt_topic_command = fields.Char(string='MQTT Command Topic', help='e.g. otm/iot/<external_id>/cmd')

    location = fields.Char(string='Location / Room')
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

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if not vals.get('device_secret'):
                vals['device_secret'] = secrets.token_hex(16)
            if not vals.get('mqtt_topic_state') and vals.get('external_id'):
                vals['mqtt_topic_state'] = 'otm/iot/%s/state' % vals['external_id']
            if not vals.get('mqtt_topic_command') and vals.get('external_id'):
                vals['mqtt_topic_command'] = 'otm/iot/%s/cmd' % vals['external_id']
        records = super().create(vals_list)
        for record in records:
            record._check_subscription_device_limit()
            if not record.channel_ids:
                record._generate_channels()
        return records

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

    def action_send_command(self, channel_no, command):
        """Queue a switch command for the bridge service to deliver (MQTT publish or Tuya API call)."""
        self.ensure_one()
        return self.env['otm.iot.device.command'].create({
            'device_id': self.id,
            'channel_no': channel_no,
            'command': command,
            'state': 'pending',
        })
