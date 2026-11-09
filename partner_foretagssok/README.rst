FöretagsAPI Partner Enrichment
==============================

Enrich ``res.partner`` records with official Swedish company data from
`FöretagsAPI.se <https://foretagsapi.se>`_.

The module replaces the scraping-based ``partner_allabolag`` approach with a
clean REST integration against ``https://data.foretagsapi.se``.

Features
--------

* Enrich individual or selected partners from the contact form or via a server
  action.
* Fetches: name, organisation number, address, SNI codes, business
  description, registration status, revenue/employee estimates and financial
  key figures.
* Integrates with ``partner_sni``: SNI codes are looked up or created and
  linked to the partner.
* Find other companies with the same SNI code and create them as contacts.
* Configurable API key and base URL in Settings -> Contacts.

Configuration
-------------

The API key is read from the system parameter ``partner_foretagssok.api_key``
first (Settings -> Contacts -> FöretagsAPI), then from the environment variable
``FORETAGSAPI_API_KEY``. No file inside the addon folder is read.

Usage
-----

* Open a company contact and click **Enrich from FöretagsAPI**.
* The rule (decision 2026-11-09): enrichment only fills empty fields. It
  never overwrites a field that has a value, and it never writes a VAT number.
* Name, organisation number and address are filled when empty. If a field has
  a different value, it is kept and the FöretagsAPI value is only mentioned in
  the chatter. There is no checkbox to overwrite it.
* If the company was found by name only, name and organisation number are not
  filled automatically. A wizard lists the proposed values for empty fields,
  one unchecked checkbox per line, and only checked lines are filled. A field
  that got a value in the meantime is refused.
* The server action on several contacts never opens a wizard: it skips name
  only matches and posts a chatter note per contact.
* The module's own fields (status, SNI codes, estimates, financials) are
  refreshed as before, they are not standard partner fields.
* If the partner has no organisation number, the module searches by name. When
  several matches exist, a notification is posted and the user must add an
  organisation number.
* When the partner has an SNI code, click **Find Similar Companies** to search
  for other companies in the same branch.

Dependencies
------------

* ``partner_enrich_base``
* ``partner_company_registry``
* ``partner_sni``
* ``mail``

License
-------

AGPL-3
