# -*- coding: utf-8 -*-
from odoo import fields, models


class IotDeviceCommand(models.Model):
    _name = 'otm.iot.device.command'
    _description = 'IoT Device Command Queue'
    _order = 'create_date desc'

    device_id = fields.Many2one('otm.iot.device', string='Device', required=True, ondelete='cascade', index=True)
    channel_no = fields.Integer(string='Channel No.', required=True)
    command = fields.Selection([
        ('on', 'Turn On'),
        ('off', 'Turn Off'),
    ], string='Command', required=True)
    state = fields.Selection([
        ('pending', 'Pending'),
        ('sent', 'Sent to Device'),
        ('acked', 'Acknowledged'),
        ('failed', 'Failed'),
    ], string='Status', default='pending', index=True)
    sent_date = fields.Datetime(string='Sent At')
    acked_date = fields.Datetime(string='Acknowledged At')
    error_message = fields.Char(string='Error')

    def action_mark_sent(self):
        self.write({'state': 'sent', 'sent_date': fields.Datetime.now()})

    def action_mark_acked(self):
        self.write({'state': 'acked', 'acked_date': fields.Datetime.now()})
        for cmd in self:
            channel = cmd.device_id.channel_ids.filtered(lambda c: c.channel_no == cmd.channel_no)
            if channel:
                channel.write({'is_on': cmd.command == 'on', 'last_changed': fields.Datetime.now()})
            cmd.env['otm.iot.device.log'].create({
                'device_id': cmd.device_id.id,
                'channel_no': cmd.channel_no,
                'event_type': cmd.command,
                'timestamp': fields.Datetime.now(),
            })

    def action_mark_failed(self, error_message=False):
        self.write({'state': 'failed', 'error_message': error_message or 'Delivery failed'})
