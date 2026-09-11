# -*- coding: utf-8 -*-
{
    'name': 'Otomater IoT Platform',
    'version': '19.0.1.0.0',
    'category': 'Internet of Things (IoT)',
    'summary': 'Multi-tenant IoT device management, switching and subscription platform',
    'description': """
Otomater IoT Platform
======================
Protocol-agnostic (MQTT / Tuya Cloud) device registry, remote on/off switching,
usage/telemetry history, and subscription-based access control for a
multi-tenant IoT SaaS offering (device control app, similar in scope to
Zoho IoT's device dashboard).

Phase 1 (this module): device registry, channel/relay model, command queue,
state/telemetry log, subscription plans + enforcement, REST API for the
customer app and for the external MQTT/Tuya bridge service.
    """,
    'author': 'Otomater',
    'website': 'https://otomater.com',
    'license': 'OPL-1',
    'depends': ['base', 'mail', 'web', 'portal'],
    'data': [
        'security/iot_security.xml',
        'security/ir.model.access.csv',
        'data/iot_sequence.xml',
        'views/iot_device_type_views.xml',
        'views/iot_device_views.xml',
        'views/iot_subscription_views.xml',
        'views/iot_menus.xml',
    ],
    'installable': True,
    'application': True,
}
