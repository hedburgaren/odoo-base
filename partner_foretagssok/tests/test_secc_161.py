# -*- coding: utf-8 -*-
"""SEC-C 161: the "Create Selected Partners" step of the similar-companies
wizard skips organisation numbers that already exist and fills the new
partners through the ordinary enrich path (mocked HTTP)."""
from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests.common import TransactionCase, tagged

from odoo.addons.partner_foretagssok.tests.test_foretagssok import (
    COMPANY, POST, _fake_post)


@tagged('post_install', '-at_install')
class TestSimilarWizardCreate(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.params = cls.env['ir.config_parameter'].sudo()
        cls.params.set_param('partner_foretagssok.api_key', 'test-key-not-real')
        cls.wizard_model = cls.env['foretagssok.similar.wizard']

    def _wizard(self, lines):
        anchor = self.env['res.partner'].create({'name': 'Utgångspunkt AB'})
        return self.wizard_model.create({
            'partner_id': anchor.id,
            'sni_code': '25110',
            'line_ids': [(0, 0, dict(line, selected=True)) for line in lines],
        })

    def test_existing_org_number_is_skipped(self):
        self.env['res.partner'].create({
            'name': 'Redan Har AB', 'company_type': 'company',
            'company_registry': '556000-1234'})
        wizard = self._wizard([
            {'name': 'Redan Har AB', 'org_number': '556000-1234',
             'street': 'Storgatan 1', 'postal_code': '58222', 'city': 'Linköping'},
            {'name': 'Ny Bolaget AB', 'org_number': '5569998887',
             'street': 'Nygatan 9', 'postal_code': '58102', 'city': 'Norrköping'},
        ])
        post = _fake_post(companies_by_org={'5569998887': dict(
            COMPANY, name='Ny Bolaget AB', orgNumber='5569998887')},
            search_results=[])
        with patch(POST, side_effect=post):
            wizard.action_create_partners()
        self.assertEqual(
            self.env['res.partner'].search_count(
                [('company_registry', 'in', ['556000-1234', '5560001234'])]),
            1, 'the existing partner must not be duplicated')
        new_partner = self.env['res.partner'].search(
            [('company_registry', 'in', ['556999-8887', '5569998887'])])
        self.assertEqual(len(new_partner), 1)
        # The enrich path ran on the new partner: its note about only
        # filling empty fields is in the chatter.
        self.assertIn('only fills empty fields',
                      ' '.join(new_partner.message_ids.mapped('body')))

    def test_all_existing_raises_and_creates_nothing(self):
        self.env['res.partner'].create({
            'name': 'Redan Har AB', 'company_type': 'company',
            'company_registry': '556000-1234'})
        wizard = self._wizard([
            {'name': 'Redan Har AB', 'org_number': '556000-1234'},
        ])
        with patch(POST, side_effect=_fake_post(search_results=[])), \
                self.assertRaises(UserError):
            wizard.action_create_partners()

    def test_nothing_selected_raises(self):
        wizard = self._wizard([
            {'name': 'Omarkerad AB', 'org_number': '556000-1234'},
        ])
        wizard.line_ids.selected = False
        with self.assertRaises(UserError):
            wizard.action_create_partners()
