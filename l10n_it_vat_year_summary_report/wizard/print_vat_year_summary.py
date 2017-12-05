# -*- coding: utf-8 -*-
##############################################################################
#    
#    Author: Alessandro Camilli (alessandrocamilli@openforce.it)
#    Copyright (C) 2014
#    Openforce di Camilli Alessandro (www.openforce.it)
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as published
#    by the Free Software Foundation, either version 3 of the License, or
#    (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


from openerp import models, fields, api, _
from openerp.exceptions import Warning as UserError


class print_vat_year_summary(models.TransientModel):
    _name = "wizard.print.vat.year.summary"
    
    fiscalyear_id = fields.Many2one(
        'account.fiscalyear', 'Fiscalyear', required=True)
    amount_generic = fields.Float('Generic Credit or Debit', readonly=True)
    amount_interest = fields.Float('Amount Interest')
    amount_paid = fields.Float('Amount Paid')
    print_page_from = fields.Integer('Page number from', default=1)
    print_page_year = fields.Char('Page number year', size=10, default=0)

    def _get_statements(self):
        period_obj = self.env['account.period']
        end_statment_vat_obj = self.env['account.vat.period.end.statement']
        # Periods competence
        domain = [('fiscalyear_id', '=', self.fiscalyear_id.id)]
        periods = period_obj.search(domain)
        period_ids = [x.id for x in periods]
        statements_competence = []
        domain = [('id', '>', 0)]
        statements = end_statment_vat_obj.search(domain)
        for statement in statements:
            statement_valid = True
            for ps in statement.period_ids:
                if ps.id not in period_ids:
                    statement_valid = False
            if statement_valid:
                statements_competence.append(statement)
        return statements_competence
    
    @api.onchange('fiscalyear_id')
    def on_change_fiscalyear_id(self):
        if self.fiscalyear_id:
            end_statment_vat_obj = self.env['account.vat.period.end.statement']
            # Statements of competence
            statements = self._get_statements()
            # Statement Generic lines
            amount_generic = 0
            for statement in statements:
                for line in statement.generic_vat_account_line_ids:
                    # credits are positive and debits are negative
                    amount_generic += line.amount * -1
            self.amount_generic = amount_generic
            # Statement Paid
            amount_paid = 0
            domain = [('state', '=', 'paid')]
            statements_paid = end_statment_vat_obj.search(domain)
            for statement in statements_paid:
                if statement not in statements:
                    continue
                if statement.authority_vat_amount > 0:
                    amount_paid += (statement.authority_vat_amount \
                                    - statement.residual)
            self.amount_paid =  amount_paid
        
    @api.v7
    def print_report(self, cr, uid, ids, context=None):
        statements = False
        wizard = self.browse(cr, uid, ids[0])
        # statements = self._get_statements(cr, uid, [], context)
        # if not statements:
        #    raise UserError(_('No documents found in the current selection'))
        
        datas = {}
        datas_form = {}
        datas_form['fiscalyear_id'] = wizard.fiscalyear_id.id
        datas_form['amount_generic'] = wizard.amount_generic
        datas_form['amount_interest'] = wizard.amount_interest
        datas_form['amount_paid'] = wizard.amount_paid
        datas_form['print_page_from'] = wizard.print_page_from
        datas_form['print_page_year'] = wizard.print_page_year
        
        report_name = 'l10n_it_vat_year_summary_report.report_vatyearsummary'
        datas = {
            'ids': statements,
            'model': 'account.vat.period.end.statement',
            'form': datas_form
        }
        return self.pool['report'].get_action(cr, uid, [], report_name, 
                                              data=datas)

