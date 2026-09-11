# -*- coding: utf-8 -*-
from odoo import fields, models


class IotDeviceLog(models.Model):
    _name = 'otm.iot.device.log'
    _description = 'IoT Device Event / Telemetry Log'
    _order = 'timestamp desc'

    device_id = fields.Many2one('otm.iot.device', string='Device', required=True, ondelete='cascade', index=True)
    channel_no = fields.Integer(string='Channel No.')
    event_type = fields.Selection([
        ('on', 'Turned On'),
        ('off', 'Turned Off'),
        ('online', 'Came Online'),
        ('offline', 'Went Offline'),
    ], string='Event', required=True)
    timestamp = fields.Datetime(string='Timestamp', required=True, default=fields.Datetime.now, index=True)
