# -*- coding: utf-8 -*-
from odoo import fields, models


class IotDeviceType(models.Model):
    _name = 'otm.iot.device.type'
    _description = 'IoT Device Type / Template'
    _order = 'name'

    name = fields.Char(string='Type Name', required=True)
    code = fields.Char(string='Code', required=True, help='Internal code, e.g. RELAY-1CH, RELAY-4CH, PLUG-TUYA')
    protocol = fields.Selection([
        ('mqtt', 'MQTT (own firmware, e.g. ESP32)'),
        ('tuya', 'Tuya Cloud (third-party smart relay/plug)'),
    ], string='Protocol', required=True, default='mqtt')
    channel_count = fields.Integer(string='Channels', default=1, help='Number of independently switchable outputs on this device type')
    icon = fields.Char(string='Icon Key', help='Icon identifier used by the customer app dashboard, e.g. "switch", "plug", "bulb"')
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)

    _code_uniq = models.Constraint('unique(code)', 'Device type code must be unique.')
