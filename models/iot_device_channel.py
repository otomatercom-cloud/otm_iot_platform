# -*- coding: utf-8 -*-
from odoo import fields, models


class IotDeviceChannel(models.Model):
    _name = 'otm.iot.device.channel'
    _description = 'IoT Device Channel (switchable output)'
    _order = 'device_id, channel_no'

    device_id = fields.Many2one('otm.iot.device', string='Device', required=True, ondelete='cascade', index=True)
    channel_no = fields.Integer(string='Channel No.', required=True)
    name = fields.Char(string='Label', required=True, help='Customer-facing name, e.g. "Living Room Light"')
    is_on = fields.Boolean(string='On', default=False)
    last_changed = fields.Datetime(string='Last Changed')

    _device_channel_uniq = models.Constraint('unique(device_id, channel_no)', 'Channel numbers must be unique per device.')

    def action_toggle(self):
        for channel in self:
            new_command = 'off' if channel.is_on else 'on'
            channel.device_id.action_send_command(channel.channel_no, new_command)
