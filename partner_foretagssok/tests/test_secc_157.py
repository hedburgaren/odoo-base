# -*- coding: utf-8 -*-
"""SEC-C 157: the multi-record enrichment uses the bulk endpoint, chunks its
lookups and keeps one failing record from rolling back the whole batch.
All HTTP is mocked, no real API and no real key is used."""
from unittest.mock import patch

from odoo.tests.common import tagged

from odoo.addons.partner_foretagssok.tests.test_foretagssok import (
    COMPANY, POST, TestForetagssok, _fake_post)

COMPANY_TWO = dict(COMPANY, name='Annat Bolaget AB',
                   orgNumber='5561112222',
                   postalAddress={'street': 'Andra Gatan 2',
                                  'postalCode': '58102', 'city': 'Norrköping'})


def _counting_fake_post(companies_by_org, counts):
    post = _fake_post(companies_by_org=companies_by_org, search_results=[])

    def wrapped(url, json=None, headers=None, timeout=None):
        if url.endswith('/v1/bulk'):
            counts['bulk'] += 1
            counts['bulk_chunk_size'] = len(json['org_numbers'])
        return post(url, json=json, headers=headers, timeout=timeout)

    return wrapped


@tagged('post_install', '-at_install')
class TestBulkEnrichment(TestForetagssok):

    def _partner(self, name, registry):
        return self._company_partner(name=name, company_registry=registry)

    def test_bulk_endpoint_lookup_and_independent_results(self):
        p1 = self._partner('Ett AB', '556000-1234')
        p2 = self._partner('Två AB', '556111-2222')
        p3 = self._partner('Tre AB', '556333-4444')
        counts = {'bulk': 0, 'bulk_chunk_size': 0}
        post = _counting_fake_post(
            {'5560001234': COMPANY, '5561112222': COMPANY_TWO}, counts)
        with patch(POST, side_effect=post):
            (p1 + p2 + p3).partner_enrich()
        # One bulk call for three records, not three single calls.
        self.assertEqual(counts['bulk'], 1)
        self.assertEqual(counts['bulk_chunk_size'], 3)
        self.assertEqual(p1.street, 'Storgatan 1')
        self.assertEqual(p2.street, 'Andra Gatan 2')
        # No org number match and no name match: noted, not crashed.
        self.assertIn('could not find', ' '.join(p3.message_ids.mapped('body')))

    def test_one_failing_record_does_not_rollback_the_batch(self):
        p1 = self._partner('Ett AB', '556000-1234')
        p2 = self._partner('Två AB', '556111-2222')
        p3 = self._partner('Tre AB', '556333-4444')
        original = type(p1)._foretagsapi_apply_company

        def failing(records, company, name_match=False, interactive=False):
            if records.id == p2.id:
                raise ValueError('simulated failure')
            return original(records, company, name_match=name_match,
                            interactive=interactive)

        post = _fake_post(companies_by_org={
            '5560001234': COMPANY, '5561112222': COMPANY_TWO})
        with patch(POST, side_effect=post):
            with patch.object(type(p1), '_foretagsapi_apply_company', failing):
                (p1 + p2 + p3).partner_enrich()
        self.assertEqual(p1.street, 'Storgatan 1',
                         'a failing record must not roll the batch back')
        self.assertFalse(p2.street)

    def test_chunking_splits_large_selections(self):
        partners = self.env['res.partner']
        companies_by_org = {}
        for i in range(51):
            org = '%010d' % (5500000000 + i)
            partner = self._partner('Bolag %d AB' % i, '%s-%s' % (org[:6], org[6:]))
            partners += partner
            companies_by_org[org] = dict(COMPANY, name=partner.name,
                                         orgNumber=org)
        counts = {'bulk': 0}
        post = _counting_fake_post(companies_by_org, counts)
        with patch(POST, side_effect=post):
            partners.partner_enrich()
        self.assertEqual(counts['bulk'], 2, '51 records need two chunks')
