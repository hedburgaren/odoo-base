# -*- coding: utf-8 -*-
from odoo import fields, models

DEFAULT_BASE_URL = 'https://data.foretagsapi.se'


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # SEC-B 2026-11-09 (finding 162): the former .env loader is gone. The key
    # lives in ir.config_parameter (this field) or, as a fallback, in the
    # environment variable FORETAGSAPI_API_KEY. No file in the addon tree is read.
    foretagssok_api_key = fields.Char(
        string='FöretagsAPI API Key',
        config_parameter='partner_foretagssok.api_key',
    )
    foretagssok_base_url = fields.Char(
        string='FöretagsAPI Base URL',
        config_parameter='partner_foretagssok.base_url',
        default=DEFAULT_BASE_URL,
    )
