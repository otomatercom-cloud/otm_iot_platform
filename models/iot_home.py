# -*- coding: utf-8 -*-
from odoo import api, fields, models


class IotHome(models.Model):
    _name = 'otm.iot.home'
    _description = 'IoT Home (a customer property containing rooms/devices)'
    _order = 'name'

    name = fields.Char(string='Home Name', required=True, default='My Home')
    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True)
    address = fields.Char(string='Address')
    room_ids = fields.One2many('otm.iot.room', 'home_id', string='Rooms')
    device_count = fields.Integer(string='Device Count', compute='_compute_device_count')
    active = fields.Boolean(default=True)

    def _compute_device_count(self):
        for home in self:
            home.device_count = self.env['otm.iot.device'].search_count([('room_id.home_id', '=', home.id)])
