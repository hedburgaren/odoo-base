# -*- coding: utf-8 -*-
# SEC-B 2026-11-09. All HTTP is mocked, no real API and no real key is used.
import os
from unittest.mock import MagicMock, patch

from odoo.tests.common import TransactionCase, tagged

POST = 'odoo.addons.partner_foretagssok.models.res_partner.requests.post'
FAKE_KEY = 'test-key-not-real'

COMPANY = {
    'name': 'Testbolaget AB',
    'orgNumber': '5560001234',
    'postalAddress': {'street': 'Storgatan 1', 'postalCode': '58222', 'city': 'Linköping'},
}


def _fake_post(companies_by_org=None, search_results=None):
    """Return a requests.post replacement routing by endpoint."""
    def post(url, json=None, headers=None, timeout=None):
        response = MagicMock()
        response.raise_for_status.return_value = None
        if url.endswith('/v1/bulk'):
            results = [
                {'success': True, 'company': (companies_by_org or {}).get(org)}
                for org in json['org_numbers']
                if (companies_by_org or {}).get(org)
            ]
            response.json.return_value = {'results': results}
        elif url.endswith('/v1/search'):
            response.json.return_value = {'companies': search_results or []}
        else:
            response.json.return_value = {}
        return response
    return post


@tagged('post_install', '-at_install')
class TestForetagssok(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.params = cls.env['ir.config_parameter'].sudo()
        cls.params.set_param('partner_foretagssok.api_key', FAKE_KEY)
        cls.Partner = cls.env['res.partner']

    def _company_partner(self, **vals):
        vals.setdefault('company_type', 'company')
        vals.setdefault('name', 'Gammalt Namn AB')
        return self.Partner.create(vals)

    def _enrich(self, partner, interactive=False, companies=None, search=None):
        post = _fake_post(
            companies_by_org={'5560001234': COMPANY} if companies is None else companies,
            search_results=search,
        )
        with patch(POST, side_effect=post):
            if interactive:
                return partner.action_foretagsapi_enrich()
            return partner.partner_enrich()

    # ---- finding 156 ------------------------------------------------------

    def test_156_empty_fields_are_filled_from_org_number_lookup(self):
        partner = self._company_partner(
            name='Testbolaget AB', company_registry='556000-1234')
        self.assertFalse(partner.street)
        self._enrich(partner)
        self.assertEqual(partner.street, 'Storgatan 1')
        self.assertEqual(partner.city, 'Linköping')
        self.assertEqual(partner.name, 'Testbolaget AB')

    def test_156_conflicting_name_is_not_overwritten_and_wizard_opens(self):
        partner = self._company_partner(company_registry='556000-1234', city='Malmö')
        action = self._enrich(partner, interactive=True)
        self.assertEqual(partner.name, 'Gammalt Namn AB')
        self.assertEqual(partner.city, 'Malmö')
        self.assertTrue(action)
        self.assertEqual(action['res_model'], 'foretagssok.enrich.wizard')
        wizard = self.env['foretagssok.enrich.wizard'].browse(action['res_id'])
        by_field = {line.field_name: line for line in wizard.line_ids}
        self.assertIn('name', by_field)
        self.assertIn('city', by_field)
        self.assertEqual(by_field['name'].current_value, 'Gammalt Namn AB')
        self.assertEqual(by_field['name'].proposed_value, 'Testbolaget AB')
        self.assertFalse(any(line.apply for line in wizard.line_ids))
        # Applying with nothing ticked writes nothing.
        wizard.action_apply()
        self.assertEqual(partner.name, 'Gammalt Namn AB')
        # Tick the name only.
        by_field['name'].apply = True
        wizard.action_apply()
        self.assertEqual(partner.name, 'Testbolaget AB')
        self.assertEqual(partner.city, 'Malmö')

    def test_156_wizard_applies_country_line(self):
        sweden = self.env.ref('base.se')
        norway = self.env.ref('base.no')
        partner = self._company_partner(
            company_registry='556000-1234', name='Testbolaget AB',
            country_id=norway.id)
        action = self._enrich(partner, interactive=True)
        wizard = self.env['foretagssok.enrich.wizard'].browse(action['res_id'])
        line = wizard.line_ids.filtered(lambda l: l.field_name == 'country_id')
        self.assertEqual(len(line), 1)
        line.apply = True
        wizard.action_apply()
        self.assertEqual(partner.country_id, sweden)

    def test_156_name_search_hit_is_never_written_directly(self):
        partner = self._company_partner(name='Testbolaget AB')
        self.assertFalse(partner.company_registry)
        action = self._enrich(partner, interactive=True, companies={}, search=[COMPANY])
        self.assertFalse(partner.company_registry)
        self.assertEqual(partner.name, 'Testbolaget AB')
        self.assertTrue(action)
        wizard = self.env['foretagssok.enrich.wizard'].browse(action['res_id'])
        line = wizard.line_ids.filtered(lambda l: l.field_name == 'company_registry')
        self.assertEqual(line.reason, 'name_match')
        self.assertFalse(line.apply)
        line.apply = True
        wizard.action_apply()
        self.assertEqual(partner.company_registry, '556000-1234')

    def test_156_wizard_rejects_fields_outside_whitelist(self):
        partner = self._company_partner()
        wizard = self.env['foretagssok.enrich.wizard'].create({
            'partner_id': partner.id,
            'line_ids': [(0, 0, {
                'field_name': 'credit_limit', 'field_label': 'x',
                'proposed_raw': '1', 'apply': True})],
        })
        from odoo.exceptions import UserError
        with self.assertRaises(UserError):
            wizard.action_apply()

    def test_156_multi_record_action_skips_conflicts_and_notes_them(self):
        p1 = self._company_partner(company_registry='556000-1234', name='Annat AB')
        p2 = self._company_partner(name='Helt Annat AB')
        post = _fake_post(
            companies_by_org={'5560001234': COMPANY}, search_results=[COMPANY])
        with patch(POST, side_effect=post):
            (p1 | p2).partner_enrich()
        self.assertEqual(p1.name, 'Annat AB')
        self.assertEqual(p2.name, 'Helt Annat AB')
        self.assertFalse(p2.company_registry)
        for partner in (p1, p2):
            bodies = ' '.join(partner.message_ids.mapped('body'))
            self.assertIn('did not apply', bodies)
        self.assertEqual(
            self.env['foretagssok.enrich.wizard'].search_count([]), 0,
            'The multi-record path must not create wizards.')

    def test_156_server_action_binding_never_opens_wizard(self):
        partner = self._company_partner(company_registry='556000-1234', name='Annat AB')
        with patch(POST, side_effect=_fake_post({'5560001234': COMPANY})):
            result = partner.partner_enrich()
        self.assertFalse(result)
        self.assertEqual(partner.name, 'Annat AB')

    # ---- finding 160 ------------------------------------------------------

    def test_160_existing_vat_is_never_overwritten(self):
        partner = self._company_partner(
            company_registry='556000-1234', name='Testbolaget AB', vat='SE556000123101')
        self._enrich(partner)
        self.assertEqual(partner.vat, 'SE556000123101')

    def test_160_empty_vat_is_not_fabricated(self):
        partner = self._company_partner(company_registry='556000-1234', name='Testbolaget AB')
        self.assertFalse(partner.vat)
        self._enrich(partner)
        self.assertFalse(partner.vat)
        vals = self.Partner._foretagsapi_map_company(COMPANY)
        self.assertNotIn('vat', vals)

    # ---- finding 162 ------------------------------------------------------

    def test_162_key_from_config_parameter_first(self):
        with patch.dict(os.environ, {'FORETAGSAPI_API_KEY': 'env-key-not-real'}):
            key, _url = self.Partner._foretagsapi_get_config()
        self.assertEqual(key, FAKE_KEY)

    def test_162_key_falls_back_to_environment_variable(self):
        self.params.set_param('partner_foretagssok.api_key', '')
        with patch.dict(os.environ, {'FORETAGSAPI_API_KEY': 'env-key-not-real'}):
            key, _url = self.Partner._foretagsapi_get_config()
        self.assertEqual(key, 'env-key-not-real')

    def test_162_no_key_anywhere_raises_user_error_and_never_reads_files(self):
        from odoo.exceptions import UserError
        self.params.set_param('partner_foretagssok.api_key', '')
        env = {k: v for k, v in os.environ.items() if k != 'FORETAGSAPI_API_KEY'}
        with patch.dict(os.environ, env, clear=True):
            with patch('builtins.open', side_effect=AssertionError('file read')):
                with self.assertRaises(UserError):
                    self.Partner._foretagsapi_ensure_config()

    def test_162_env_loader_is_gone(self):
        self.assertFalse(hasattr(self.env['res.config.settings'], 'load_env_api_key'))
        import odoo.addons.partner_foretagssok as pkg
        self.assertFalse(hasattr(pkg, 'post_init_hook'))
