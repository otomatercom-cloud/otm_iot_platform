# -*- coding: utf-8 -*-
from odoo import api, fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    iot_subscription_plan_id = fields.Many2one('otm.iot.subscription.plan', string='Current IoT Plan')
    iot_subscription_valid_until = fields.Datetime(string='IoT Subscription Valid Until')
    iot_subscription_active = fields.Boolean(string='IoT Subscription Active', compute='_compute_iot_subscription_active', store=True)
    iot_max_devices = fields.Integer(string='Max IoT Devices', related='iot_subscription_plan_id.max_devices', store=True)
    iot_device_ids = fields.One2many('otm.iot.device', 'partner_id', string='IoT Devices')
    iot_device_count = fields.Integer(string='IoT Device Count', compute='_compute_iot_device_count')
    iot_payment_ids = fields.One2many('otm.iot.subscription.payment', 'partner_id', string='IoT Subscription Payments')

    @api.depends('iot_subscription_valid_until')
    def _compute_iot_subscription_active(self):
        now = fields.Datetime.now()
        for partner in self:
            partner.iot_subscription_active = bool(
                partner.iot_subscription_valid_until and partner.iot_subscription_valid_until >= now
            )

    def _compute_iot_device_count(self):
        for partner in self:
            partner.iot_device_count = len(partner.iot_device_ids)

    def _update_iot_subscription_state(self):
        """Recompute plan/expiry from the latest payment; called after a new payment is recorded."""
        for partner in self:
            latest = self.env['otm.iot.subscription.payment'].search(
                [('partner_id', '=', partner.id)], order='valid_until desc', limit=1
            )
            if latest:
                partner.iot_subscription_plan_id = latest.plan_id
                partner.iot_subscription_valid_until = latest.valid_until

    def action_renew_iot_subscription(self, plan_id=False, payment_reference=False):
        self.ensure_one()
        plan = self.env['otm.iot.subscription.plan'].browse(plan_id) if plan_id else self.iot_subscription_plan_id
        if not plan:
            return False
        return self.env['otm.iot.subscription.payment'].create({
            'partner_id': self.id,
            'plan_id': plan.id,
            'payment_reference': payment_reference,
        })
