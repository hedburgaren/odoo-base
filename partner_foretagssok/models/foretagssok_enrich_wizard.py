# -*- coding: utf-8 -*-
# SEC-B 2026-11-09 (finding 156): confirmation step for identity and address
# data proposed by FöretagsAPI.
from markupsafe import Markup

from odoo import _, fields, models
from odoo.exceptions import UserError

from .res_partner import CONFIRM_FIELDS


class ForetagssokEnrichWizard(models.TransientModel):
    _name = 'foretagssok.enrich.wizard'
    _description = 'Confirm FöretagsAPI Changes'

    partner_id = fields.Many2one(
        'res.partner', string='Partner', required=True, readonly=True,
        ondelete='cascade')
    line_ids = fields.One2many(
        'foretagssok.enrich.wizard.line', 'wizard_id', string='Proposed changes')

    def action_apply(self):
        """Fill the checked lines, with the rights of the current user.

        SEC-B decision 2026-11-09: only empty fields are ever filled. The
        partner is re-checked here, a line whose field has a value by now
        is refused (left unchanged) and named in the chatter.
        """
        self.ensure_one()
        vals = {}
        applied = []
        refused = []
        for line in self.line_ids.filtered('apply'):
            fname = line.field_name
            if fname not in CONFIRM_FIELDS:
                raise UserError(_('This field cannot be changed from here: %s') % fname)
            if self.partner_id._foretagsapi_field_is_set(fname):
                refused.append(line)
                continue
            if fname == 'country_id':
                vals[fname] = int(line.proposed_raw)
            else:
                vals[fname] = line.proposed_raw
            applied.append(line)
        if vals:
            self.partner_id.write(vals)
            empty = _('(empty)')
            items = Markup('').join(
                Markup('<li>%s: %s / %s</li>') % (
                    line.field_label,
                    line.current_value or empty,
                    line.proposed_value,
                ) for line in applied
            )
            self.partner_id.message_post(
                body=Markup('%s<ul>%s</ul>') % (
                    _('Confirmed and applied from FöretagsAPI '
                      '(previous value / new value):'),
                    items,
                ),
                message_type='notification',
            )
        if refused:
            self.partner_id.message_post(
                body=Markup('%s<ul>%s</ul>') % (
                    _('FöretagsAPI only fills empty fields. These fields '
                      'already have a value and were left unchanged:'),
                    Markup('').join(
                        Markup('<li>%s</li>') % line.field_label
                        for line in refused),
                ),
                message_type='notification',
            )
        return {'type': 'ir.actions.act_window_close'}


class ForetagssokEnrichWizardLine(models.TransientModel):
    _name = 'foretagssok.enrich.wizard.line'
    _description = 'FöretagsAPI Proposed Change'

    wizard_id = fields.Many2one(
        'foretagssok.enrich.wizard', string='Wizard', required=True,
        ondelete='cascade')
    field_name = fields.Char(string='Technical Field', readonly=True)
    field_label = fields.Char(string='Field', readonly=True)
    current_value = fields.Char(string='Current Value', readonly=True)
    proposed_value = fields.Char(string='Proposed Value', readonly=True)
    proposed_raw = fields.Char(string='Proposed Raw Value', readonly=True)
    reason = fields.Selection(
        selection=[
            ('name_match', 'Matched by name only'),
        ],
        string='Reason', readonly=True)
    apply = fields.Boolean(string='Apply', default=False)
