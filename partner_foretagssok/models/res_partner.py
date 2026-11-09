# -*- coding: utf-8 -*-
import logging
import os
import re

import requests
from markupsafe import Markup, escape

from odoo import _, api, fields, models
from odoo.exceptions import UserError

from .foretagsapi_mapping import ForetagsapiMappingMixin

_logger = logging.getLogger(__name__)

DEFAULT_BASE_URL = 'https://data.foretagsapi.se'
ENV_API_KEY_NAME = 'FORETAGSAPI_API_KEY'

# SEC-B 2026-11-09 (findings 156, 160): fields that enrichment may only fill
# when empty, never overwrite. A differing value is only reported; name and
# org. number from a name-only match go through a confirmation step.
IDENTITY_FIELDS = ('name', 'company_registry')
ADDRESS_FIELDS = ('street', 'zip', 'city', 'country_id')
CONFIRM_FIELDS = IDENTITY_FIELDS + ADDRESS_FIELDS


class ResPartnerFinancials(models.Model):
    _name = 'res.partner.financials'
    _description = 'Partner Financials from FöretagsAPI'
    _order = 'fiscal_year desc'

    partner_id = fields.Many2one(
        'res.partner',
        string='Partner',
        required=True,
        ondelete='cascade',
    )
    fiscal_year = fields.Char(string='Fiscal Year')
    fiscal_year_start = fields.Date(string='Fiscal Year Start')
    fiscal_year_end = fields.Date(string='Fiscal Year End')
    taxonomy = fields.Char(string='Taxonomy')
    currency = fields.Char(string='Currency')

    net_sales = fields.Float(string='Net Sales')
    operating_profit = fields.Float(string='Operating Profit')
    net_result = fields.Float(string='Net Result')
    result_after_financial_items = fields.Float(string='Result After Financial Items')
    profit_before_tax = fields.Float(string='Profit Before Tax')
    total_assets = fields.Float(string='Total Assets')
    equity = fields.Float(string='Equity')
    current_assets = fields.Float(string='Current Assets')
    current_liabilities = fields.Float(string='Current Liabilities')
    cash_and_bank = fields.Float(string='Cash and Bank')
    long_term_liabilities = fields.Float(string='Long Term Liabilities')
    fixed_assets = fields.Float(string='Fixed Assets')
    restricted_equity = fields.Float(string='Restricted Equity')
    unrestricted_equity = fields.Float(string='Unrestricted Equity')
    untaxed_reserves = fields.Float(string='Untaxed Reserves')
    proposed_dividend = fields.Float(string='Proposed Dividend')
    employees = fields.Integer(string='Employees')
    solidity = fields.Float(string='Solvency')
    operating_margin = fields.Float(string='Operating Margin')


class ResPartner(models.Model, ForetagsapiMappingMixin):
    _inherit = 'res.partner'

    foretagssok_business_description = fields.Text(string='Business Description')
    foretagssok_registration_date = fields.Date(string='Registration Date')
    foretagssok_deregistration_date = fields.Date(string='Deregistration Date')
    foretagssok_status = fields.Char(string='Company Status')
    foretagssok_revenue_estimate = fields.Float(string='Revenue Estimate')
    foretagssok_employees_estimate = fields.Integer(string='Employees Estimate')
    foretagssok_estimates_reference_year = fields.Char(string='Estimates Reference Year')
    foretagssok_financial_ids = fields.One2many(
        'res.partner.financials',
        'partner_id',
        string='Financials',
    )

    # -------------------------------------------------------------------------
    # Configuration helpers
    # -------------------------------------------------------------------------

    @api.model
    def _foretagsapi_get_config(self):
        """Return (api_key, base_url).

        SEC-B 2026-11-09 (finding 162): the key is read from
        ir.config_parameter first, then from the environment variable
        FORETAGSAPI_API_KEY. No file inside the addon tree is ever read.
        """
        params = self.env['ir.config_parameter'].sudo()
        api_key = (params.get_param('partner_foretagssok.api_key', default='') or '').strip()
        if not api_key:
            api_key = (os.environ.get(ENV_API_KEY_NAME) or '').strip()
        base_url = (params.get_param(
            'partner_foretagssok.base_url',
            default=DEFAULT_BASE_URL,
        ) or DEFAULT_BASE_URL).strip().rstrip('/')
        return api_key, base_url

    @api.model
    def _foretagsapi_ensure_config(self):
        api_key, base_url = self._foretagsapi_get_config()
        if not api_key:
            raise UserError(_(
                'FöretagsAPI API key is missing. Add it in Settings -> Contacts, '
                'or set the environment variable FORETAGSAPI_API_KEY on the server.'
            ))
        return api_key, base_url

    # -------------------------------------------------------------------------
    # API client
    # -------------------------------------------------------------------------

    @api.model
    def _foretagsapi_request(self, endpoint, payload):
        api_key, base_url = self._foretagsapi_ensure_config()
        url = f'{base_url}{endpoint}'
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json',
        }
        try:
            response = requests.post(
                url,
                json=payload,
                headers=headers,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            _logger.error('FöretagsAPI HTTP error %s: %s', e.response.status_code, e.response.text)
            if e.response.status_code == 401:
                raise UserError(_('FöretagsAPI authentication failed. Check your API key.'))
            raise UserError(_('FöretagsAPI returned an error: %s') % e.response.text)
        except requests.exceptions.RequestException as e:
            _logger.error('FöretagsAPI request error: %s', e)
            raise UserError(_('Could not reach FöretagsAPI: %s') % e)

    @api.model
    def _foretagsapi_search_by_name(self, name, limit=5):
        if not name:
            return []
        result = self._foretagsapi_request('/v1/search', {'q': name, 'limit': limit})
        return result.get('companies', [])

    @api.model
    def _foretagsapi_lookup_by_org_numbers(self, org_numbers):
        """Look up one or many organisation numbers via the bulk endpoint."""
        if not org_numbers:
            return []
        digits = [re.sub(r'\D', '', str(o)) for o in org_numbers if o]
        digits = [d for d in digits if len(d) == 10]
        if not digits:
            return []
        result = self._foretagsapi_request('/v1/bulk', {'org_numbers': digits})
        return [
            item.get('company')
            for item in result.get('results', [])
            if item.get('success') and item.get('company')
        ]

    @api.model
    def _foretagsapi_search_by_sni(
        self,
        sni_code,
        city=None,
        min_revenue=None,
        max_revenue=None,
        has_annual_report=None,
        exact_only=None,
        sort_by=None,
        limit=100,
        offset=0,
    ):
        if not sni_code:
            return []
        payload = {'sni_code': sni_code, 'limit': limit, 'offset': offset}
        if city:
            payload['city'] = city
        if min_revenue is not None:
            payload['minRevenue'] = min_revenue
        if max_revenue is not None:
            payload['maxRevenue'] = max_revenue
        if has_annual_report is not None:
            payload['hasAnnualReport'] = has_annual_report
        if exact_only is not None:
            payload['exactOnly'] = exact_only
        if sort_by:
            payload['sort'] = sort_by
        result = self._foretagsapi_request('/v1/sni/search', payload)
        return result.get('companies', [])

    # -------------------------------------------------------------------------
    # Enrichment
    # -------------------------------------------------------------------------

    def partner_enrich(self):
        """Override partner_enrich_base to fetch from FöretagsAPI."""
        # Only the single-record button sets this context key: it may open the
        # confirmation wizard. The multi-record server action never does, it
        # skips what needs confirmation and notes it in the chatter.
        interactive = len(self) == 1 and bool(
            self.env.context.get('foretagsapi_interactive'))
        action = False
        for partner in self:
            result = partner._foretagsapi_enrich_single(interactive=interactive)
            if result:
                action = result
        # Keep the chain alive for other enrich modules
        if hasattr(super(ResPartner, self), 'partner_enrich'):
            super(ResPartner, self).partner_enrich()
        return action

    def _foretagsapi_enrich_single(self, interactive=False):
        self.ensure_one()
        if self.company_type != 'company':
            self.message_post(
                body=_('FöretagsAPI enrichment is only available for companies.'),
                message_type='notification',
            )
            return

        company = False
        name_match = False
        if self.company_registry:
            companies = self._foretagsapi_lookup_by_org_numbers([self.company_registry])
            company = companies[0] if companies else False

        if not company and self.name:
            companies = self._foretagsapi_search_by_name(self.name, limit=5)
            if len(companies) == 1:
                company = companies[0]
                name_match = True
            elif len(companies) > 1:
                self.message_post(
                    body=_(
                        'FöretagsAPI found several matches for "%s". '
                        'Please provide an organisation number and try again.'
                    ) % self.name,
                    message_type='notification',
                )
                return

        if not company:
            self.message_post(
                body=_('FöretagsAPI could not find any company for %s.') % (self.name or self.display_name),
                message_type='notification',
            )
            return

        return self._foretagsapi_apply_company(
            company, name_match=name_match, interactive=interactive)

    # -- confirmation of identity and address data (SEC-B finding 156) ------

    def _foretagsapi_field_is_set(self, fname):
        value = self[fname]
        if fname == 'country_id':
            return bool(value)
        return bool((value or '').strip())

    def _foretagsapi_same_value(self, fname, proposed):
        if fname == 'country_id':
            return self.country_id.id == proposed
        current = (self[fname] or '').strip()
        proposed = (proposed or '').strip()
        if fname == 'company_registry':
            return re.sub(r'\D', '', current) == re.sub(r'\D', '', proposed)
        return current.casefold() == proposed.casefold()

    def _foretagsapi_split_confirmations(self, vals, name_match):
        """Remove from ``vals`` everything that must not be written directly.

        SEC-B decision 2026-11-09 (finding 160): enrichment only fills empty
        fields, it never overwrites. Name, org. number and address fields:
        * non-empty and equal to the API value: nothing to do;
        * non-empty and different: a conflict, never applicable, only
          reported (read-only, chatter note);
        * empty: written directly, except name and org. number from a
          name-only match, which wait for confirmation in the wizard.
        Returns (items to confirm, conflicts), both lists of dicts.
        """
        self.ensure_one()
        items = []
        conflicts = []
        for fname in CONFIRM_FIELDS:
            if fname not in vals:
                continue
            proposed = vals[fname]
            is_set = self._foretagsapi_field_is_set(fname)
            if is_set and self._foretagsapi_same_value(fname, proposed):
                vals.pop(fname)
                continue
            if not is_set and not (name_match and fname in IDENTITY_FIELDS):
                continue  # plain fill of an empty field, written directly
            vals.pop(fname)
            if fname == 'country_id':
                current_display = self.country_id.display_name or ''
                proposed_display = self.env['res.country'].browse(proposed).display_name or ''
                proposed_raw = str(proposed)
            else:
                current_display = self[fname] or ''
                proposed_display = proposed
                proposed_raw = proposed
            item = {
                'field_name': fname,
                'field_label': self._fields[fname]._description_string(self.env),
                'current_value': current_display,
                'proposed_value': proposed_display,
                'proposed_raw': proposed_raw,
            }
            if is_set:
                conflicts.append(item)
            else:
                items.append(dict(item, reason='name_match'))
        return items, conflicts

    def _foretagsapi_conflict_note(self, conflicts):
        lines = Markup('').join(
            Markup('<li>%s: %s / %s</li>') % (
                item['field_label'],
                item['current_value'],
                item['proposed_value'],
            ) for item in conflicts
        )
        return Markup('%s<ul>%s</ul>') % (
            _('FöretagsAPI enrichment only fills empty fields. These fields '
              'already have a value and were left unchanged '
              '(current value / value from FöretagsAPI):'),
            lines,
        )

    def _foretagsapi_skipped_note(self, items):
        empty = _('(empty)')
        lines = Markup('').join(
            Markup('<li>%s: %s / %s</li>') % (
                item['field_label'],
                item['current_value'] or empty,
                item['proposed_value'],
            ) for item in items
        )
        return Markup('%s<ul>%s</ul>') % (
            _('FöretagsAPI found a match by name only, so these empty fields '
              'were not filled (current value / proposed value). Open the '
              'contact and use "Enrich from FöretagsAPI" to confirm them:'),
            lines,
        )

    def _foretagsapi_open_confirm_wizard(self, items):
        self.ensure_one()
        wizard = self.env['foretagssok.enrich.wizard'].create({
            'partner_id': self.id,
            'line_ids': [(0, 0, dict(item, apply=False)) for item in items],
        })
        return {
            'type': 'ir.actions.act_window',
            'name': _('Confirm FöretagsAPI changes'),
            'res_model': 'foretagssok.enrich.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
        }

    def _foretagsapi_apply_company(self, company, name_match=False, interactive=False):
        self.ensure_one()
        vals = self._foretagsapi_map_company(company)
        if not vals:
            return False

        confirm_items, conflicts = self._foretagsapi_split_confirmations(
            vals, name_match)

        # Replace financials for the same fiscal year instead of duplicating
        if 'foretagssok_financial_ids' in vals:
            new_financials = vals.pop('foretagssok_financial_ids')
            fiscal_year = False
            for command in new_financials:
                if command[0] == 0 and command[2].get('fiscal_year'):
                    fiscal_year = command[2]['fiscal_year']
                    break
            if fiscal_year:
                existing = self.foretagssok_financial_ids.filtered(
                    lambda f: f.fiscal_year == fiscal_year
                )
                if existing:
                    existing.unlink()
            vals['foretagssok_financial_ids'] = new_financials

        self.write(vals)

        message = self._foretagsapi_enrichment_message(company, vals)
        self.message_post(body=message, message_type='notification')

        if conflicts:
            self.message_post(
                body=self._foretagsapi_conflict_note(conflicts),
                message_type='notification',
            )

        if confirm_items:
            if interactive:
                return self._foretagsapi_open_confirm_wizard(confirm_items)
            self.message_post(
                body=self._foretagsapi_skipped_note(confirm_items),
                message_type='notification',
            )
        return False

    def _foretagsapi_enrichment_message(self, company, vals):
        name = company.get('name', '')
        org = company.get('orgNumber', '')
        return _('Partner enriched from FöretagsAPI: %s (org. %s)') % (name, org)

    # -------------------------------------------------------------------------
    # Actions
    # -------------------------------------------------------------------------

    def action_foretagsapi_enrich(self):
        return self.with_context(foretagsapi_interactive=True).partner_enrich()

    def action_foretagsapi_find_similar(self):
        self.ensure_one()
        if not self.sni_id:
            raise UserError(_('This company has no SNI code to search from.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Companies with SNI %s') % self.sni_id.code,
            'res_model': 'foretagssok.similar.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_partner_id': self.id,
                'default_sni_code': self.sni_id.code,
                'default_sni_name': self.sni_id.name,
            },
        }
