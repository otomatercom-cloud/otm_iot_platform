# -*- coding: utf-8 -*-
from odoo import fields, models


class IotRoom(models.Model):
    _name = 'otm.iot.room'
    _description = 'IoT Room (within a Home)'
    _order = 'home_id, name'

    name = fields.Char(string='Room Name', required=True)
    home_id = fields.Many2one('otm.iot.home', string='Home', required=True, ondelete='cascade', index=True)
    partner_id = fields.Many2one('res.partner', related='home_id.partner_id', store=True, string='Customer')
    icon = fields.Char(string='Icon Key', help='e.g. "livingroom", "bedroom", "kitchen" - used by the app for room icons')
    device_ids = fields.One2many('otm.iot.device', 'room_id', string='Devices')
    device_count = fields.Integer(string='Device Count', compute='_compute_device_count')
    active = fields.Boolean(default=True)

    def _compute_device_count(self):
        for room in self:
            room.device_count = len(room.device_ids)
