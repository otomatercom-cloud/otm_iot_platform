# -*- coding: utf-8 -*-
from datetime import timedelta

from odoo import api, fields, models


class IotSubscriptionPayment(models.Model):
    _name = 'otm.iot.subscription.payment'
    _description = 'IoT Subscription Payment / Renewal'
    _order = 'payment_date desc'

    partner_id = fields.Many2one('res.partner', string='Customer', required=True, index=True)
    plan_id = fields.Many2one('otm.iot.subscription.plan', string='Plan', required=True)
    # Snapshotted at payment time so later plan price/duration edits never rewrite past records
    plan_name = fields.Char(string='Plan Name (at payment)', required=True)
    amount = fields.Monetary(string='Amount Paid', required=True)
    currency_id = fields.Many2one('res.currency', string='Currency', default=lambda self: self.env.company.currency_id)
    duration_days = fields.Integer(string='Duration (Days, at payment)', required=True)
    payment_date = fields.Datetime(string='Payment Date', required=True, default=fields.Datetime.now)
    valid_until = fields.Datetime(string='Valid Until', compute='_compute_valid_until', store=True)
    payment_reference = fields.Char(string='Payment Reference', help='Gateway transaction ID (Razorpay) or bank transfer UTR/reference')

    payment_method = fields.Selection([
        ('online', 'Online (Razorpay)'),
        ('bank_transfer', 'Bank Transfer'),
    ], string='Payment Method', default='online', required=True)

    # Online payments are verified server-side (signature check) before this record is even
    # created, so they default verified. Bank transfers can't be auto-verified - they sit
    # pending until an admin confirms the money actually arrived, and only THEN count toward
    # the customer's active subscription (see res.partner._update_iot_subscription_state).
    verified = fields.Boolean(string='Verified', default=True)
    verified_date = fields.Datetime(string='Verified At')
    verified_by = fields.Many2one('res.users', string='Verified By')
    customer_note = fields.Char(string='Customer Note', help='Free-text note the customer entered when submitting a bank transfer, e.g. sender name/bank')

    @api.depends('payment_date', 'duration_days')
    def _compute_valid_until(self):
        for rec in self:
            if rec.payment_date and rec.duration_days:
                rec.valid_until = rec.payment_date + timedelta(days=rec.duration_days)
            else:
                rec.valid_until = rec.payment_date

    @api.model_create_multi
    def create(self, vals_list):
        Plan = self.env['otm.iot.subscription.plan']
        for vals in vals_list:
            if vals.get('plan_id') and not vals.get('plan_name'):
                plan = Plan.browse(vals['plan_id'])
                vals['plan_name'] = plan.name
                vals.setdefault('amount', plan.price)
                vals.setdefault('duration_days', plan.duration_days)
            if vals.get('payment_method') == 'bank_transfer':
                vals.setdefault('verified', False)
        records = super().create(vals_list)
        for record in records:
            if record.verified:
                record.partner_id._update_iot_subscription_state()
        return records

    def action_verify_payment(self):
        """Admin confirms a bank transfer actually arrived - activates the subscription."""
        for record in self:
            if record.verified:
                continue
            record.write({
                'verified': True,
                'verified_date': fields.Datetime.now(),
                'verified_by': self.env.user.id,
            })
            record.partner_id._update_iot_subscription_state()
