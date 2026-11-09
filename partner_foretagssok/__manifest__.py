# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo SA, Open Source Management Solution, third party addon
#    Copyright (C) 2024- Vertel AB (<https://vertel.se>).
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program. If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################

{
    'name': 'Base: Enrich partner information from FöretagsAPI',
    # SEC-B 2026-11-09: 18.0.1.1.0, enrichment fills only empty identity fields
    # (confirmation wizard), no fabricated VAT, API key from config parameter
    # or FORETAGSAPI_API_KEY, .env loader removed.
    # SEC-B decision 2026-11-09: 18.0.1.2.0, fill-empty-only, never overwrite;
    # a conflicting value is reported in the chatter, never applicable.
    # SEC-C 2026-11-09: 18.0.1.3.0, bulk enrichment in chunks of 50 with a
    # savepoint per record, SNI creates in a savepoint, the similar wizard
    # skips existing organisation numbers and enriches what it creates.
    'version': '18.0.1.3.0',
    'summary': 'Enrich partner with data from FöretagsAPI.se',
    'category': 'Website',
    'description': """
    Enrich partner records with data from FöretagsAPI.se.

    The module uses the official REST API at https://data.foretagsapi.se to
    fetch company information such as name, organisation number, address,
    SNI codes, business description, registration status and financial key
    figures. It also makes it possible to find other companies within the
    same SNI branch.
    """,
    'author': 'ARC Gruppen AB | Chrille Hedberg | https://arcgruppen.se | info@arcgruppen.se',
    'website': 'https://arcgruppen.se',
    'license': 'AGPL-3',
    'contributor': '',
    'maintainer': 'Vertel AB',
    'repository': 'https://github.com/vertelab/odoo-base',
    'depends': [
        'partner_enrich_base',
        'partner_company_registry',
        'partner_sni',
        'mail',
    ],
    'data': [
        'security/ir.model.access.csv',
        'data/ir_actions_server.xml',
        'views/res_config_settings_views.xml',
        'views/res_partner_views.xml',
    ],
    'application': False,
    'installable': True,
}
# vim:expandtab:smartindent:tabstop=4:softtabstop=4:shiftwidth=4:
