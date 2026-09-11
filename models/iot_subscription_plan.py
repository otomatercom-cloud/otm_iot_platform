# -*- coding: utf-8 -*-
from odoo import fields, models


class IotSubscriptionPlan(models.Model):
    _name = 'otm.iot.subscription.plan'
    _description = 'IoT Subscription Plan'
    _order = 'price'

    name = fields.Char(string='Plan Name', required=True)
    price = fields.Monetary(string='Price', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    duration_days = fields.Integer(string='Validity (Days)', required=True, default=30)
    max_devices = fields.Integer(string='Max Devices', required=True, default=5)
    description = fields.Text(string='Description')
    active = fields.Boolean(default=True)
