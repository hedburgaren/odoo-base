# partner_foretagssok

## Purpose
Enrich `res.partner` records with official Swedish company data from
[FöretagsAPI.se](https://foretagsapi.se) via the REST API at
`https://data.foretagsapi.se`.

The module was created as a clean replacement for `partner_allabolag`, which
relied on web scraping through Tor.

Version 18.0.1.2.0 (SEC-B decision 2026-11-09, findings 156 and 160) changes
how enrichment writes data and where the API key comes from, see below.

**The rule: enrichment only fills empty fields. It never overwrites a field
that has a value, and it never writes `vat`.**

## Data flow
1. User triggers enrichment from the partner form button
   (`action_foretagsapi_enrich`, single record, may open the confirmation
   wizard) or from the server action "Enrich with FöretagsAPI" (any number of
   records, never opens a wizard).
2. If `company_registry` is set, the module calls `POST /v1/bulk`.
3. Otherwise (or if that finds nothing) it calls `POST /v1/search` by name. A
   single hit is used, several hits stop with a chatter note. A match found this
   way is a "name match".
4. The response is mapped to Odoo fields: name, org. number, address, SNI codes,
   business description, status, estimates and financials. `vat` is not mapped.
5. The mapped values are split (`_foretagsapi_split_confirmations`):
   * `name`, `company_registry`, `street`, `zip`, `city`, `country_id` are
     written directly only when the partner's field is empty.
   * If the partner has a different non-empty value, the proposal is a
     conflict: never written, never applicable, only listed in a chatter note.
   * For a name match, `name` and `company_registry` are never written
     directly, not even into empty fields (they wait for the wizard).
   * The module's own data (`foretagssok_*` fields, financials, SNI links
     `sni_id`/`sni_ids` from partner_sni) is refreshed as before. None of these
     is a standard partner field, so the fill-empty-only rule does not apply.
6. A chatter message summarises what was written.

## Confirmation flow
Models `foretagssok.enrich.wizard` and `foretagssok.enrich.wizard.line`
(transient, access for `base.group_user`, the same users that can enrich).
Each line holds field, current value, proposed value, reason (only
`name_match`) and an `apply` checkbox, default off. Conflicts never become
lines.
* Single record, button: the wizard opens only when a name-only match left
  empty name or org. number fields to confirm. "Apply selected" fills only the
  checked lines with the rights of the current user and posts a chatter note.
  Only the six fields above are accepted, any other `field_name` raises a
  UserError. At apply time each line is re-checked: if the partner field has a
  value by then, the line is refused (left unchanged) and named in the chatter.
* Multi record, server action: no wizard. Name-only matches are skipped and
  one chatter note per partner lists current and proposed values.
* Conflicts (both paths): one chatter note lists current value and API value.

## VAT
Enrichment never sets `vat`. The earlier code built `SE` + org. number + `01`,
which is not a verified VAT number. The mapped API response has no VAT
registration flag, so there is nothing to base a fill on.

## SNI integration
The module depends on `partner_sni`. SNI codes returned by the API are looked
up or created in `res.sni` and linked through `sni_id` and `sni_ids`.

The **Find Similar Companies** action uses `POST /v1/sni/search` to find other
companies with the same SNI code. Results are shown in a transient wizard and
can be created as new partners.

## Configuration
Base URL is stored in `ir.config_parameter` `partner_foretagssok.base_url`
(default `https://data.foretagsapi.se`).

API key, read by `res.partner._foretagsapi_get_config` in this order:
1. `ir.config_parameter` `partner_foretagssok.api_key` (also editable in
   Settings -> Contacts).
2. Environment variable `FORETAGSAPI_API_KEY` of the Odoo process.

No file inside the addon tree is read. The former `.env` loader and the
`post_init_hook` were removed, so install and upgrade work with no key at all;
enrichment then raises a UserError that names both places.

## Models
* `res.partner` - extended with FöretagsAPI-specific fields and enrichment
  methods.
* `res.partner.financials` - one row per fiscal year with key figures from
  digital annual reports.
* `foretagssok.similar.wizard` / `foretagssok.similar.wizard.line` - transient
  models for the SNI similarity search.
* `foretagssok.enrich.wizard` / `foretagssok.enrich.wizard.line` - transient
  models for the confirmation step.

## Security
Access rights are defined in `security/ir.model.access.csv`.

## Tests
`tests/test_foretagssok.py`, TransactionCase, `requests.post` mocked, no real
API and no real key.

## External dependencies
Only Odoo-bundled libraries. HTTP calls use `requests` (shipped with Odoo).
