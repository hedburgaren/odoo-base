# -*- coding: utf-8 -*-
"""SEC-C 159: a failed SNI create rolls back only that SNI row.

``except Exception`` without a savepoint around the create meant a database
error on one SNI row poisoned the whole transaction: the enrichment failed
for every record in the batch. The create now runs in a savepoint, so one
bad SNI code costs only that link.
"""
from unittest.mock import patch

from odoo.tests.common import TransactionCase, tagged

from odoo.addons.partner_foretagssok.tests.test_foretagssok import (
    COMPANY, POST, TestForetagssok, _fake_post)

COMPANY_WITH_SNI = dict(COMPANY, sniCodes={
    'sni1': '25110', 'sni1_name': 'Byggentreprenad'})


@tagged('post_install', '-at_install')
class TestSniSavepoint(TestForetagssok):

    def test_failed_sni_create_does_not_abort_enrichment(self):
        partner = self._company_partner(
            name='Testbolaget AB', company_registry='556000-1234')
        post = _fake_post(companies_by_org={'5560001234': COMPANY_WITH_SNI})
        with patch(POST, side_effect=post):
            with patch.object(type(self.env['res.sni']), 'create',
                              side_effect=ValueError('bad SNI row')):
                partner._foretagsapi_enrich_single(interactive=False)
        # The enrichment survived the failing SNI row and wrote everything else.
        self.assertEqual(partner.street, 'Storgatan 1')
        self.assertFalse(partner.sni_id)

    def test_working_sni_creates_are_kept(self):
        partner = self._company_partner(
            name='Testbolaget AB', company_registry='556000-1234')
        post = _fake_post(companies_by_org={'5560001234': COMPANY_WITH_SNI})
        with patch(POST, side_effect=post):
            partner._foretagsapi_enrich_single(interactive=False)
        self.assertTrue(partner.sni_id)
        self.assertEqual(partner.sni_id.code, '25110')
