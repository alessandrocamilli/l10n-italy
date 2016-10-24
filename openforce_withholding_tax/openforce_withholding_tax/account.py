# -*- coding: utf-8 -*-
##############################################################################
#    
#    Author: Alessandro Camilli (alessandrocamilli@openforce.it)
#    Copyright (C) 2014
#    Openforce (<http://www.openforce.it>)
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

from openerp.osv import orm, fields
from openerp.tools.translate import _
import openerp.addons.decimal_precision as dp
from openerp import netsvc

class account_move(orm.Model):
    _inherit = "account.move"
    
    def _prepare_wt_values(self, cr, uid, ids, context=None):
        assert len(ids) == 1, 'This option should only be used for a single id at a time.'
        partner = False
        wt_competence = {}
        
        move = self.browse(cr, uid, ids[0])
        # Fist : Partner and WT competence
        for line in move.line_id:
            if line.partner_id:
                partner = line.partner_id
                if partner.property_account_position:
                    for wt in partner.property_account_position.withholding_tax_ids:
                        wt_competence[wt.id] = {
                                'withholding_tax_id': wt.id,
                                'partner_id': partner.id,
                                'date': move.date,
                                'account_move_id': move.id,
                                'wt_account_move_line_id': False,
                                'base': 0,
                                'amount': 0,
                            } 
                            
                break
        # After : Loking for WT lines
        for move in self.browse(cr, uid, ids):
            base = 0
            wt_amount = 0
            for line in move.line_id:
                domain = []
                # WT line
                if line.credit:
                    domain.append(('account_payable_id', '=', \
                                                    line.account_id.id))
                    amount = line.credit
                else:
                    domain.append(('account_receivable_id', '=', \
                                                    line.account_id.id))
                    amount = line.debit
                wt_ids = self.pool['withholding.tax'].search(cr, uid, 
                                                             domain)
                if wt_ids:
                    wt_amount += amount
                    if wt_competence[wt_ids[0]] \
                        and 'amount' in wt_competence[wt_ids[0]]:
                        wt_competence[wt_ids[0]]['wt_account_move_line_id'] =\
                                                line.id
                        wt_competence[wt_ids[0]]['amount'] = wt_amount
                        wt_competence[wt_ids[0]]['base'] = \
                            self.pool['withholding.tax'].get_base_from_tax(
                                                cr, uid, 
                                                wt_ids[0], wt_amount)
                # WT Base 
                #if line.account_id.type in ['other']:
        
        wt_codes = []
        if wt_competence:
            for key, val in wt_competence.items():
                wt_codes.append(val)
        res = {
            'partner_id' : partner.id,
            'move_id' : move.id,
            'invoice_id' : False,
            'date' : move.date,
            'base': wt_codes[0]['base'],
            'tax': wt_codes[0]['amount'],
            'withholding_tax_id' : wt_codes[0]['withholding_tax_id'],
            'wt_account_move_line_id' : wt_codes[0]['wt_account_move_line_id'],
            'amount' : wt_codes[0]['amount'],
            #'move_ids' : False,   
        }                
        
        return res

class account_move_line(orm.Model):
    _inherit = "account.move.line"
    _columns = {
            'withholding_tax_amount': fields.float('Withholding Tax Amount'),
        }
    
class account_voucher(orm.Model):
    _inherit = "account.voucher"
    
    def recompute_voucher_lines(self, cr, uid, ids, partner_id, journal_id, price, currency_id, ttype, date, context=None):
        '''
        Compute original amount of WT of rate
        '''
        move_line_obj = self.pool['account.move.line']
        voucher_line_obj = self.pool['account.voucher.line']
        dp_obj = self.pool['decimal.precision']
        res = super(account_voucher, self).recompute_voucher_lines(cr, uid, ids, 
                                                                   partner_id,
                                                                   journal_id,
                                                                   price,
                                                                   currency_id,
                                                                   ttype, date,
                                                                   context=context)
        def _compute_wt_values(lines):
            amount_overflow_residual = 0.0
            # For each line, WT
            for line in lines:
                if 'move_line_id' in line and line['move_line_id']:
                    move_line = move_line_obj.browse(cr, uid, line['move_line_id'])
                    line['amount_original_withholding_tax'] = move_line.withholding_tax_amount
                    line['amount_residual_withholding_tax']= \
                            voucher_line_obj.compute_amount_residual_withholdin_tax(cr, uid, 
                                                                    line, 
                                                                    context=None)
            # Recompute automatic values on amount: 
            # The amount_residual_currency on account_move_line, doesn't see the WT values
            if lines and lines[0]['amount']:
                # For each amount to redistribuite
                tot_amount = 0
                for line in lines:
                    tot_amount += line['amount'] + line['amount_residual_withholding_tax']
                
                # Redistribuite amount
                tot_amount_paid = tot_amount
                extra_amount = 0
                for line in lines:
                    if tot_amount <= 0:
                        break
                    save_amount = line['amount']
                    line['amount'] += extra_amount
                    if line['amount'] > (line['amount_unreconciled'] - line['amount_residual_withholding_tax']):
                        line['amount'] = line['amount_unreconciled'] - line['amount_residual_withholding_tax']
                        line['amount'] = round(line['amount'], dp_obj.precision_get(cr, uid, 'Account'))
                    extra_amount += (save_amount - line['amount'])
                    tot_amount -= line['amount'] 
            # Allocate WT 
            for line in lines:
                if 'move_line_id' in line and line['move_line_id']:
                    move_line = move_line_obj.browse(cr, uid, line['move_line_id'])
                    if line['amount'] or amount_overflow_residual:
                        amount_with_wt = line['amount'] 
                        # Assign overflow from other lines
                        if amount_overflow_residual:
                            if (line['amount'] + amount_overflow_residual) <= (line['amount_unreconciled'] - line['amount_residual_withholding_tax']):
                                line['amount'] += amount_overflow_residual
                                amount_overflow_residual = 0.0
                            else:
                                line['amount'] = line['amount_unreconciled'] - line['amount_residual_withholding_tax']
                        # Compute WT
                        line['amount_withholding_tax']= \
                            voucher_line_obj.compute_amount_withholdin_tax(cr, uid, line['amount'],
                                                            line['amount_unreconciled'], 
                                                            line['amount_residual_withholding_tax'], 
                                                            context=None)
                        # WT can generate an overflow. It will bw assigned to next line
                        amount_overflow = line['amount'] + line['amount_withholding_tax'] - line['amount_unreconciled']
                        if amount_overflow > 0 :
                            line['amount'] -= amount_overflow
                            amount_overflow_residual += amount_overflow
                    line['amount_original'] -= line['amount_original_withholding_tax']
                    
            return lines
        if partner_id:
            lines_dr  = res['value']['line_dr_ids']
            lines_dr = _compute_wt_values(lines_dr)
            lines_cr  = res['value']['line_cr_ids']
            lines_cr = _compute_wt_values(lines_cr)
        
        return res
    
    def voucher_move_line_create(self, cr, uid, voucher_id, line_total, move_id, company_currency, current_currency, context=None):
        '''
        Add WT line to registration and change amount on debit/credit line of the invoice 
        '''
        move_line_obj = self.pool['account.move.line']
        voucher_line_obj = self.pool['account.voucher.line']
        payment_term_obj = self.pool['account.payment.term']
        reconcile_obj = self.pool['account.move.reconcile']
        line_total, rec_list_ids  = super(account_voucher, self).voucher_move_line_create(cr, uid,
                                                                    voucher_id,
                                                                    line_total,
                                                                    move_id,
                                                                    company_currency,
                                                                    current_currency, 
                                                                    context=context)
        def _unreconcile_move_line(move_line):
            '''
            Remove reconciliation to change amounts
            '''
            recs = []
            recs_to_rereconcile = []
            if move_line.reconcile_id:
                recs += [move_line.reconcile_id.id]
            if move_line.reconcile_partial_id:
                recs += [move_line.reconcile_partial_id.id]
                # If there are other partial payments, I save the id line to future reconcile
                cr.execute('SELECT id FROM account_move_line WHERE reconcile_partial_id=%s \
                                AND id <> %s', 
                            (move_line.reconcile_partial_id.id, move_line.id))
                for l in cr.dictfetchall():
                    recs_to_rereconcile.append(l['id'])
            reconcile_obj.unlink(cr, uid, recs)
            return recs_to_rereconcile
        
        # rec_list_ids id payment move line with invoice move_line to reconcile
        rec_list_new_moves = []
        for rec in rec_list_ids:
            line_move_to_pay = move_line_obj.browse(cr, uid, rec[1])
            line_payment = move_line_obj.browse(cr, uid, rec[0])
            # Remove reconciliation to change amounts
            lines_to_rereconcile = _unreconcile_move_line(line_move_to_pay)
            for r_line_id in lines_to_rereconcile:
                rec_list_new_moves.append([r_line_id, line_move_to_pay.id])
            _unreconcile_move_line(line_payment)
            # line voucher with WT
            domain = [('voucher_id', '=', voucher_id), ('move_line_id', '=', line_move_to_pay.id)]
            v_line_payment_ids = voucher_line_obj.search(cr, uid, domain)
            for v_line in voucher_line_obj.browse(cr, uid, v_line_payment_ids):
                voucher = v_line.voucher_id
                tot_credit = 0.0
                tot_debit = 0.0
                for wt_v_line in v_line.withholding_tax_line_ids:
                    credit = 0.0
                    debit = 0.0
                    if v_line.move_line_id.debit:
                        debit = wt_v_line.amount
                    else:
                        credit = wt_v_line.amount
                    # account
                    if line_move_to_pay.account_id.type == 'receivable':
                        wt_account_id = wt_v_line.withholding_tax_id.account_receivable_id.id
                    else:
                        wt_account_id = wt_v_line.withholding_tax_id.account_payable_id.id
                    # Line WT
                    payment_lines = payment_term_obj.compute(cr,
                        uid, wt_v_line.withholding_tax_id.payment_term.id, wt_v_line.amount,
                        voucher.date or False, context=context)
                    line_wt_ids = []
                    for payment_line in payment_lines:
                        p_date_maturity = payment_line[0]
                        p_credit = 0.0
                        p_debit = 0.0
                        if debit:
                            p_debit = payment_line[1]
                        else:
                            p_credit = payment_line[1]
                        val_move_line = {
                            'journal_id': voucher.journal_id.id,
                            'period_id': voucher.period_id.id,
                            #'name': wt_v_line.withholding_tax_id.name or '/',
                            'name': wt_v_line.withholding_tax_id.name + ' ' + voucher.partner_id.name or '/',
                            'account_id': wt_account_id,
                            'move_id': move_id,
                            #'partner_id': voucher.partner_id.id,
                            'partner_id': False,
                            'currency_id': v_line.move_line_id.currency_id.id or False,
                            'analytic_account_id': v_line.account_analytic_id and v_line.account_analytic_id.id or False,
                            'quantity': 1,
                            'credit': p_credit,
                            'debit': p_debit,
                            'date': voucher.date,
                            'date_maturity': p_date_maturity
                        }
                        line_wt_id = move_line_obj.create(cr, uid, val_move_line)
                        line_wt_ids.append(line_wt_id)
                    tot_credit += credit
                    tot_debit += debit
                    
                # Add amount WT to line debit/credit partner
                val = {
                    'credit': line_payment.credit + tot_debit,
                    'debit': line_payment.debit + tot_credit
                    }
                move_line_obj.write(cr, uid, [line_payment.id], val)
                    
        # Merge with existing lines to reconcile
        if rec_list_new_moves:
            for rec_new in rec_list_new_moves:
                for rec_ids in rec_list_ids:
                    if not rec_new[1] == rec_ids[1]:
                        continue
                    rec_ids.append(rec_new[0])
        
        return (line_total, rec_list_ids)
    
    def action_move_line_create(self, cr, uid, ids, context=None):
        '''
        Assign payment move to wt lines
        '''
        res = super(account_voucher, self).action_move_line_create(cr, uid, 
                                                            ids, context=None)
        for voucher in self.browse(cr, uid, ids):
            for v_line in voucher.line_ids:
                for wt_v_line in v_line.withholding_tax_line_ids:
                    self.pool['withholding.tax.voucher.line']._align_wt_move(
                                                    cr, uid, [wt_v_line.id])
        return res
    
    
class account_voucher_line(orm.Model):
    _inherit = "account.voucher.line"
    
    def _amount_withholding_tax(self, cr, uid, ids, name, args, context=None):
        res = {}
        for line in self.browse(cr, uid, ids, context=context):
            res[line.id] = {
                'amount_original_withholding_tax': 0.0,
            }
            res[line.id]['amount_original_withholding_tax'] += line.move_line_id.withholding_tax_amount
        return res
    
    def _compute_balance(self, cr, uid, ids, name, args, context=None):
        '''
        Extends the compute of original amounts for exclude from total the WT amount
        '''
        currency_pool = self.pool.get('res.currency')
        rs_data = {}
        for line in self.browse(cr, uid, ids, context=context):
            ctx = context.copy()
            ctx.update({'date': line.voucher_id.date})
            voucher_rate = self.pool.get('res.currency').read(cr, uid, line.voucher_id.currency_id.id, ['rate'], context=ctx)['rate']
            ctx.update({
                'voucher_special_currency': line.voucher_id.payment_rate_currency_id and line.voucher_id.payment_rate_currency_id.id or False,
                'voucher_special_currency_rate': line.voucher_id.payment_rate * voucher_rate})
            res = {}
            company_currency = line.voucher_id.journal_id.company_id.currency_id.id
            voucher_currency = line.voucher_id.currency_id and line.voucher_id.currency_id.id or company_currency
            move_line = line.move_line_id or False

            if not move_line:
                res['amount_original'] = 0.0
                res['amount_unreconciled'] = 0.0
                res['amount_withholding_tax'] = 0.0
            elif move_line.currency_id and voucher_currency==move_line.currency_id.id:
                res['amount_original'] = abs(move_line.amount_currency - move_line.withholding_tax_amount) # modify for WT
                res['amount_unreconciled'] = abs(move_line.amount_residual_currency)
            else:
                #always use the amount booked in the company currency as the basis of the conversion into the voucher currency
                res['amount_original'] = currency_pool.compute(cr, uid, company_currency, voucher_currency, move_line.credit or move_line.debit or 0.0, context=ctx)
                res['amount_unreconciled'] = currency_pool.compute(cr, uid, company_currency, voucher_currency, abs(move_line.amount_residual), context=ctx)
                res['amount_original'] -= move_line.withholding_tax_amount # add for WT
                
            rs_data[line.id] = res
        return rs_data
    
    _columns = {
            'amount_original': fields.function(_compute_balance, multi='dc', type='float', string='Original Amount', store=True, digits_compute=dp.get_precision('Account')),
            'amount_original_withholding_tax': fields.function(_amount_withholding_tax, 
                       digits_compute=dp.get_precision('Account'), string='Withholding Tax Original', multi='withholding_tax'),
            'amount_residual_withholding_tax': fields.float('Withholding Tax Amount Residual'),
            'amount_withholding_tax': fields.float('Withholding Tax Amount'),
            'withholding_tax_line_ids': fields.one2many('withholding.tax.voucher.line', 'voucher_line_id', 'Withholding Tax Lines'),
        }
    
    def onchange_amount(self, cr, uid, ids, amount, amount_unreconciled, amount_residual_withholding_tax, context=None):
        res = super(account_voucher_line, self).onchange_amount(cr, uid, ids, 
                                                                amount, 
                                                                amount_unreconciled, 
                                                                context=context)
        dp_obj = self.pool['decimal.precision']
        wt_amount = self.compute_amount_withholdin_tax(cr, uid, amount, amount_unreconciled, amount_residual_withholding_tax, context)
        res['value'].update({'amount_withholding_tax': wt_amount})
        
        # Setting for Total amount
        if (amount + wt_amount) >= round(amount_unreconciled,dp_obj.precision_get(cr, uid, 'Account')):
            res['value'].update({'reconcile': True})
            res['value'].update({'amount': amount})

        return res
    
    def onchange_reconcile(self, cr, uid, ids, reconcile, amount, 
                           amount_unreconciled, 
                           amount_residual_withholding_tax, 
                           context=None):
        '''
        TO CONSIDER: Amount tot = amount net + amount WT 
        '''
        res = super(account_voucher_line, self).onchange_reconcile(cr, uid, ids, 
                                                                reconcile,
                                                                amount, 
                                                                amount_unreconciled, 
                                                                context=context)
        if reconcile: 
            amount = amount_unreconciled
            wt_amount = self.compute_amount_withholdin_tax(cr, uid, amount, amount_unreconciled, amount_residual_withholding_tax, context)
            res['value']['amount'] = amount - wt_amount
        return res
    
    def compute_amount_residual_withholdin_tax(self, cr, uid, line, context=None):
        '''
        WT residual = WT amount original - (All WT amounts in voucher posted)
        '''
        dp_obj = self.pool['decimal.precision']
        wt_amount_residual = 0.0
        if not 'move_line_id' in line or not line['move_line_id']:
            return wt_amount_residual
        domain = [('move_line_id', '=', line['move_line_id'])]
        v_line_ids = self.search(cr, uid, domain)
        wt_amount_residual = line['amount_original_withholding_tax']
        for v_line in self.browse(cr, uid, v_line_ids):
            if v_line.voucher_id.state == 'posted':
                wt_amount_residual -= v_line.amount_withholding_tax
        
        return wt_amount_residual
        
    def compute_amount_withholdin_tax(self, cr, uid, amount, amount_unreconciled, wt_amount_residual, context=None):
        dp_obj = self.pool['decimal.precision']
        wt_amount = 0.0
        # Total amount
        amount_tot = amount + wt_amount_residual
        base_amount = amount_unreconciled - wt_amount_residual
        if amount_tot >= round(amount_unreconciled,dp_obj.precision_get(cr, uid, 'Account')):
            wt_amount = wt_amount_residual
        # Partial amount ( ratio with amount net)
        else:
            wt_amount = round(wt_amount_residual * (1.0 * amount / base_amount),\
                              dp_obj.precision_get(cr, uid, 'Account'))
        return wt_amount
    
    def recompute_withholding_tax_voucher_line(self, cr, uid, voucher_line_id, context=None):
        '''
        Split amount voucher line second WT lines invoice
        '''
        res = []
        invoice_obj = self.pool['account.invoice']
        wt_voucher_line_obj = self.pool['withholding.tax.voucher.line']
        dp_obj = self.pool['decimal.precision']
        
        voucher_line = self.browse(cr, uid, voucher_line_id)
        # delete existing wt lines
        domain = [('voucher_line_id', '=', voucher_line_id)]
        wtv_line_ids = wt_voucher_line_obj.search(cr, uid, domain)
        wt_voucher_line_obj.unlink(cr, uid, wtv_line_ids)
        #
        if voucher_line.amount_withholding_tax:
            domain = [('move_id', '=', voucher_line.move_line_id.move_id.id)]
            inv_ids = invoice_obj.search(cr, uid, domain)
            for inv in invoice_obj.browse(cr, uid, inv_ids):
                if len(inv.withholding_tax_line):
                    rate_num  = len(inv.withholding_tax_line)
                    # Coeff for more wt
                    coeff_residual = 1
                    wt_residual = voucher_line.amount_withholding_tax
                    i = 0
                    for wtl in inv.withholding_tax_line:
                        i += 1
                        if i == rate_num:
                            coeff = coeff_residual
                        else:
                            coeff = \
                                wtl.tax / wtl.invoice_id.withholding_tax_amount
                        coeff_residual -= coeff
                        
                        # Rates
                        wt_amount_rate = \
                            round(voucher_line.amount_withholding_tax * coeff, 
                                  dp_obj.precision_get(cr, uid, 'Account'))
                        wt_amount = 0
                        if i == rate_num:
                            wt_amount = wt_residual
                        else: 
                            wt_amount = wt_amount_rate
                        wt_residual -= wt_amount
                        val = {
                            'voucher_line_id' : voucher_line_id,
                            'withholding_tax_id' : wtl.withholding_tax_id.id,
                            'amount' : wt_amount
                            }
                        wt_voucher_line_obj.create(cr, uid, val)
                    
        return res
    
    def create(self, cr, uid, vals, *args, **kwargs):
        res_id = super(account_voucher_line,self).create(cr, uid, vals, *args, **kwargs)
        self.recompute_withholding_tax_voucher_line(cr, uid, res_id, context=None)
        return res_id
    
    def write(self, cr, uid, ids, vals, context=None):
        res = super(account_voucher_line,self).write(cr, uid, ids, vals, context)
        if 'amount_withholding_tax' in vals:
            for line_id in ids:
                self.recompute_withholding_tax_voucher_line(cr, uid, line_id)
        return res
    
    
class account_fiscal_position(orm.Model):
    _inherit = "account.fiscal.position"
    _columns = {
            'withholding_tax_ids': fields.many2many('withholding.tax', 'account_fiscal_position_withholding_tax_rel', 'fiscal_position_id', 'withholding_tax_id', 'Withholding Tax'),
        }
    
class account_invoice(orm.Model):
    _inherit = "account.invoice"
    
    def _amount_withholding_tax(self, cr, uid, ids, name, args, context=None):
        res = {}
        dp_obj = self.pool['decimal.precision']
        for invoice in self.browse(cr, uid, ids, context=context):
            res[invoice.id] = {
                'withholding_tax_amount': 0.0,
            }
            for line in invoice.withholding_tax_line:
                res[invoice.id]['withholding_tax_amount'] += \
                    round(line.tax, dp_obj.precision_get(cr, uid, 'Account'))
            res[invoice.id]['amount_net_pay'] = invoice.amount_total - res[invoice.id]['withholding_tax_amount']
        return res
    
    _columns = {
        'withholding_tax': fields.boolean('Withholding Tax'),
        'withholding_tax_line': fields.one2many('account.invoice.withholding.tax', 'invoice_id', 'Withholding Tax', readonly=True, states={'draft':[('readonly',False)]}),
        'withholding_tax_amount': fields.function(_amount_withholding_tax, digits_compute=dp.get_precision('Account'), string='Withholding tax', multi='withholding_tax'),
        'amount_net_pay': fields.function(_amount_withholding_tax, digits_compute=dp.get_precision('Account'), string='Net To Pay', multi='withholding_tax')
        }
    
    def action_move_create(self, cr, uid, ids, context=None):
        '''
        Split amount withholding tax on account move lines
        '''
        wt_inv_obj = self.pool['account.invoice.withholding.tax']
        move_line_obj = self.pool['account.move.line']
        dp_obj = self.pool['decimal.precision']
        
        res = super(account_invoice, self).action_move_create(cr, uid, ids, context=context)
        
        for inv in self.browse(cr, uid, ids):
            # Rates
            rate_num = 0
            for move_line in inv.move_id.line_id:
                if not move_line.date_maturity:
                    continue
                rate_num += 1
            #
            if rate_num:
                wt_rate = round(inv.withholding_tax_amount / rate_num, \
                                dp_obj.precision_get(cr, uid, 'Account'))
            wt_residual = inv.withholding_tax_amount
            # Re-read move lines to assign the amounts of wt
            i = 0
            for move_line in inv.move_id.line_id:
                if not move_line.date_maturity:
                    continue
                i += 1
                if i == rate_num:
                    wt_amount = wt_residual
                else:
                    wt_amount = wt_rate
                wt_residual -= wt_amount
                # update line
                move_line_obj.write(cr, uid, [move_line.id], {'withholding_tax_amount': wt_amount})
        
            # Align with WT statement
            for wt_inv_line in inv.withholding_tax_line:
                wt_inv_obj._align_statement(cr, uid, [wt_inv_line.id])
        
        return res
    
    def compute_all_withholding_tax(self, cr, uid, ids, context=None):
        
        withholdin_tax_obj = self.pool['withholding.tax']
        invoice_withholdin_tax_obj = self.pool['account.invoice.withholding.tax']
        res ={}
        
        if not ids :
            return res
        
        for invoice in self.browse(cr, uid, ids):
            # Clear for recompute o because there isn't withholding_tax to True 
            if invoice.fiscal_position or not invoice.withholding_tax:
                cr.execute("DELETE FROM account_invoice_withholding_tax WHERE invoice_id=%s ", (invoice.id,))
            if invoice.fiscal_position and invoice.fiscal_position.withholding_tax_ids:
                for tax in invoice.fiscal_position.withholding_tax_ids:
                    tot_invoice = 0
                    withholding_tax = withholdin_tax_obj.compute_amount(cr, uid, tax.id, tot_invoice, invoice.id, context=None)
                    val = {
                        'invoice_id' : invoice.id,
                        'withholding_tax_id' : tax.id,
                        'base': withholding_tax['base'],
                        'tax': withholding_tax['tax']
                        }
                    invoice_withholdin_tax_obj.create(cr, uid, val)
        
        return res
    
    def button_reset_taxes(self, cr, uid, ids, context=None):
        res = super(account_invoice, self).button_reset_taxes(cr, uid, ids, context=context)
        
        self.compute_all_withholding_tax(cr, uid, ids, context)
        
        return res
    
    def onchange_fiscal_position_id(self, cr, uid, ids, fiscal_position_id, context=None):
        res ={}
        fiscal_position_obj = self.pool['account.fiscal.position']
        vals= False
        if fiscal_position_id:
            fiscal_position = fiscal_position_obj.browse(cr, uid, fiscal_position_id)
            use_wt = False
            if fiscal_position.withholding_tax_ids:
                use_wt= True
            vals = {
                'withholding_tax': use_wt
                }
        
        res = {
            'value': vals   
            }
        return res
    
    
class account_invoice_line(orm.Model):
    _inherit = "account.invoice.line"
    
    def compute_amount_line(self, cr, uid, line):
        
        dp_obj = self.pool['decimal.precision']
        price_subtotal = 0  
        price = line['price_unit'] * (1-(line['discount'] or 0.0)/100.0)
        if 'discount2' in line: # field of my customization
            price = price * (1-(line['discount2'] or 0.0)/100.0)
        price_subtotal = round(price * line['quantity'], dp_obj.precision_get(cr, uid, 'Account'))
        
        return price_subtotal


class account_invoice_withholding_tax(orm.Model):
    _name = 'account.invoice.withholding.tax'
    _description = 'Invoice Withholding Tax Line'
    _columns = {
            'invoice_id': fields.many2one('account.invoice', 'withholding_tax_line', 
                            'Invoice', ondelete="cascade"),
            'withholding_tax_id': fields.many2one('withholding.tax', 'Withholding tax'),
            'base': fields.float('Base'),
            'tax': fields.float('Tax'),
        }
    
    def _align_statement(self, cr, uid, ids, context=None):
        '''
        Align statement values with wt lines invoice
        '''
        wt_st_id =False
        wt_statement_obj = self.pool['withholding.tax.statement']
        for wt_inv_line in self.browse(cr, uid, ids):
            domain = [('move_id', '=', wt_inv_line.invoice_id.move_id.id),
                      ('withholding_tax_id', '=', wt_inv_line.withholding_tax_id.id)]
            wt_st_ids = wt_statement_obj.search(cr, uid, domain)
            # Create statemnt if doesn't exist
            if not wt_st_ids:
                vals = {
                    'date' : wt_inv_line.invoice_id.move_id.date,
                    'move_id' : wt_inv_line.invoice_id.move_id.id,
                    'invoice_id' : wt_inv_line.invoice_id.id,
                    'partner_id' : wt_inv_line.invoice_id.partner_id.id,
                    'withholding_tax_id' : wt_inv_line.withholding_tax_id.id,
                }
                wt_st_id = wt_statement_obj.create(cr, uid, vals)
            else:
                wt_st_id = wt_st_ids[0]
            # Update values
            vals = {
                'base': wt_inv_line.base,
                'tax': wt_inv_line.tax
            }
            wt_statement_obj.write(cr, uid, [wt_st_id], vals)
            
        return wt_st_id
    
    def onchange_withholding_tax_id(self, cr, uid, ids, withholding_tax_id, invoice_line_ids):
        fiscal_position_obj = self.pool['account.fiscal.position']
        withholdin_tax_obj = self.pool['withholding.tax']
        invoice_line_obj = self.pool['account.invoice.line']
        res = {}
        tot_invoice = 0
        for line in invoice_line_ids:
            if line[1]:
                line_inv = invoice_line_obj.browse(cr, uid, line[1])
                price_subtotal = line_inv.price_subtotal
            else:
                price_subtotal = invoice_line_obj.compute_amount_line(cr, uid, line[2])
            tot_invoice += price_subtotal
        tax = withholdin_tax_obj.compute_amount(cr, uid, withholding_tax_id, tot_invoice, invoice_id=None, context=None)
        
        res['value'] = {
                'base': tax['base'],
                'tax': tax['tax']
                }
        
        return res
  
class withholding_tax(orm.Model):
    _name = 'withholding.tax'
    _description = 'Withholding Tax'
    
    def _get_rate(self, cr, uid, ids, field_names, args, context=None):
        res = {}
        for tax in self.browse(cr, uid, ids, context=context):
            cr.execute('SELECT tax, base FROM withholding_tax_rate ' \
                    ' WHERE withholding_tax_id = %s and (date_start <= current_date or date_start is null)' \
                    ' ORDER by date_start LIMIT 1', (tax.id,))
            rate = cr.fetchone()
            if rate:
                res[tax.id] = {
                        'tax' : rate[0],
                        'base': rate[1]
                        }
            else:
                res[tax.id] = {
                        'tax' : 0,
                        'base': 1
                        }
                
        return res
    
    _columns = {
            'active': fields.boolean('Active'),
            'name': fields.char('Name', size=256, required=True),
            'certification': fields.boolean('Certification'),
            'comment': fields.text('Text'),
            'account_receivable_id': fields.many2one('account.account', 'Account Receivable', required=True, 
                    domain=[('type','=', 'receivable')]),
            'account_payable_id': fields.many2one('account.account', 'Account Payable', required=True, 
                    domain=[('type','=', 'payable')]),
            'payment_term': fields.many2one('account.payment.term', 'Payment Terms', required=True),
            'tax': fields.function(_get_rate, string='Tax %', multi='balance'),
            'base': fields.function(_get_rate, string='Base', multi='balance'),
            'rate_ids': fields.one2many('withholding.tax.rate', 'withholding_tax_id', 'Rates', required=True),
        }
    _defaults = {
            'active': True
        }
    
    def compute_amount(self, cr, uid, withholding_tax_id, amount_invoice, invoice_id=None, context=None):
        invoice_obj = self.pool['account.invoice']
        res = {
            'base' : 0,
            'tax' : 0
            }
        if not amount_invoice and invoice_id:
            invoice = invoice_obj.browse(cr, uid, invoice_id)
            amount_invoice = invoice.amount_untaxed
        tax = self.browse(cr, uid, withholding_tax_id)
        base = amount_invoice * tax.base
        tax = base * ((tax.tax or 0.0)/100.0)
        
        res['base'] = base
        res['tax'] = tax
        
        return res
    
    def get_base_from_tax(self, cr, uid, withholding_tax_id, wt_amount):
        '''
        100 * wt_amount        1
        ---------------  *  -------
              % tax          Coeff
        '''
        dp_obj = self.pool['decimal.precision']
        base = 0
        if wt_amount:
            wt = self.browse(cr, uid, withholding_tax_id)
            base = round( (100 * wt_amount / wt.tax) * (1 / wt.base), \
                            dp_obj.precision_get(cr, uid, 'Account') )
        return base
    

class withholding_tax_rate(orm.Model):
    _name = 'withholding.tax.rate'
    _description = 'Withholding Tax Rates'
    
    def _check_date(self, cursor, user, ids, context=None):
        for rate in self.browse(cursor, user, ids, context=context):
            if not rate.withholding_tax_id.active:
                continue
            where = []
            if rate.date_start:
                where.append("((date_stop>='%s') or (date_stop is null))" % (rate.date_start,))
            if rate.date_stop:
                where.append("((date_start<='%s') or (date_start is null))" % (rate.date_stop,))

            cursor.execute('SELECT id ' \
                    'FROM withholding_tax_rate ' \
                    'WHERE '+' and '.join(where) + (where and ' and ' or '')+
                        'withholding_tax_id = %s ' \
                        'AND id <> %s', (
                            rate.withholding_tax_id.id,
                            rate.id))
            if cursor.fetchall():
                return False
        return True

    _columns = {
            'withholding_tax_id': fields.many2one('withholding.tax', 'Withholding Tax', ondelete='cascade', readonly=True),
            'date_start': fields.date('Date Start'),
            'date_stop': fields.date('Date Stop'),
            'comment': fields.text('Text'),
            'base': fields.float('Base Coeff.'),
            'tax': fields.float('Tax %'),
        }
    _defaults = {
            'base': 1
        }
    
    _constraints = [
        (_check_date, 'You cannot have 2 pricelist versions that overlap!',
            ['date_start', 'date_stop'])
    ]

class withholding_tax_voucher_line(orm.Model):
    _name = 'withholding.tax.voucher.line'
    _description = 'Withholding Tax Voucher Line'
    _columns = {
            'voucher_line_id': fields.many2one('account.voucher.line', 'Account Voucher Line', ondelete='cascade'),
            'withholding_tax_id': fields.many2one('withholding.tax', 'Withholding Tax'),
            'amount': fields.float('Amount'),
        }
    
    def _align_wt_move(self, cr, uid, ids, context=None):
        '''
        Align with wt move lines
        '''
        wt_statement_obj = self.pool['withholding.tax.statement']
        wt_move_obj = self.pool['withholding.tax.move']
        wt_invoice_obj = self.pool['account.invoice.withholding.tax']
        for wt_v_line in self.browse(cr, uid, ids):
             # Search statemnt of competence
            domain = [('move_id', '=', 
                    wt_v_line.voucher_line_id.move_line_id.move_id.id),
                    ('withholding_tax_id', '=', 
                    wt_v_line.withholding_tax_id.id)]
            wt_st_ids = wt_statement_obj.search(cr, uid, domain)
            if wt_st_ids:
                wt_st_id = wt_st_ids[0]
            else:
                wt_st_id = False
            
            # Create move if doesn't exist
            domain = [('wt_voucher_line_id', '=', wt_v_line.id),
                      ('move_line_id', '=', False)]
            wt_move_ids = wt_move_obj.search(cr, uid, domain)
            wt_move_vals = {
                'statement_id': wt_st_id, 
                'date': wt_v_line.voucher_line_id.voucher_id.date,
                'partner_id': 
                    wt_v_line.voucher_line_id.voucher_id.partner_id.id,
                'wt_voucher_line_id': wt_v_line.id,
                'withholding_tax_id': wt_v_line.withholding_tax_id.id, 
                'account_move_id': 
                    wt_v_line.voucher_line_id.voucher_id.move_id.id,
                'date_maturity': 
                    wt_v_line.voucher_line_id.move_line_id.date_maturity            
                }
            if not wt_move_ids:
                wt_move_id = wt_move_obj.create(cr, uid, wt_move_vals)
            else:
                wt_move_id = wt_move_ids[0]
            # Update values
            wt_move_vals.update({'amount': wt_v_line.amount})
            wt_move_obj.write(cr, uid, [wt_move_id], wt_move_vals)
            
        return True
    
    def create(self, cr, uid, vals, *args, **kwargs):
        res_id = super(withholding_tax_voucher_line, self).create(cr, uid, 
                                                    vals, *args, **kwargs)
        # Align with wt move
        self._align_wt_move(cr, uid, [res_id])
        return res_id
    
    def write(self, cr, uid, ids, vals, context=None):
        res = super(withholding_tax_voucher_line, self).write(cr, uid, 
                                                        ids, vals, context)
        # Align with wt move
        self._align_wt_move(cr, uid, ids)
        return res
    
class withholding_tax_statement(orm.Model):
    _name = 'withholding.tax.statement'
    _description = 'Withholding Tax Statement'
    
    def _get_current_statement(self, cr, uid, ids, name, context=None):
        statement_ids = []
        tax_move_obj = self.pool['withholding.tax.move']
        for move in tax_move_obj.browse(cr, uid, ids, context=context):
            statement_ids.append(move.statement_id.id)
        return statement_ids
    
    def _compute_total(self, cr, uid, ids, field_names, args, context=None):
        res = {}
        for line in self.browse(cr, uid, ids, context=context):
            tot_wt_amount = 0
            tot_wt_amount_paid = 0
            for wt_move in line.move_ids:
                tot_wt_amount += wt_move.amount
                if wt_move.state == 'paid':
                    tot_wt_amount_paid += wt_move.amount
            res[line.id] = {
                'amount': tot_wt_amount,
                'amount_paid': tot_wt_amount_paid,
            }
        return res
    
    _columns = {
            'date': fields.date('Date'), 
            'move_id': fields.many2one('account.move', 'Account move', ondelete='cascade'),
            'invoice_id': fields.many2one('account.invoice', 'Invoice', ondelete='cascade'),
            'partner_id': fields.many2one('res.partner', 'Partner'),
            'withholding_tax_id': fields.many2one('withholding.tax', 'Withholding Tax'),
            'base': fields.float('Base'),
            'tax': fields.float('Tax'),
            'amount': fields.function(_compute_total, 
                    string='WT amount', multi='total',
                    store={'withholding.tax.move': (
                                    _get_current_statement, 
                                    ['amount',], 
                                    20),
                        },),
            'amount_paid': fields.function(_compute_total, 
                    string='WT amount paid', multi='total',
                    store={'withholding.tax.move': (
                                    _get_current_statement, 
                                    ['state',], 
                                    20),
                        },),
            'move_ids': fields.one2many('withholding.tax.move', 
                                'statement_id', 'Moves'),
        }
    
class withholding_tax_move(orm.Model):
    _name = 'withholding.tax.move'
    _description = 'Withholding Tax Move'
    
    _columns = {
            'state': fields.selection([
                ('due', 'Due'),
                ('paid', 'Paid'),
                ], 'Status', readonly=True, copy=False, select=True),
            'statement_id': fields.many2one('withholding.tax.statement', 
                                    'Statement'),
            'date': fields.date('Date Competence'), 
            'wt_voucher_line_id': fields.many2one('withholding.tax.voucher.line', 
                                    'WT Account Voucher Line', ondelete='cascade'),
            'move_line_id': fields.many2one('account.move.line', 
                        'Account Move line', ondelete='cascade',
                        help="Used from trace WT from other parts(BS)"),
            'withholding_tax_id': fields.many2one('withholding.tax', 'Withholding Tax'),
            'amount': fields.float('Amount'),
            'partner_id': fields.many2one('res.partner', 'Partner'),
            'date_maturity' : fields.date('Date Maturity'),
            'account_move_id': fields.many2one('account.move', 'Account Move', 
                                 ondelete='cascade')
        }
    _defaults = {
            'state' : 'due'
        }
    
    def action_paid(self, cr, uid, ids, context=None):
        for pt in self.browse(cr, uid, ids):
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, self._name, 
                                    pt.id, 'paid', cr)
        return True
    
    def action_set_to_draft(self, cr, uid, ids, context=None):
        for pt in self.browse(cr, uid, ids):
            wf_service = netsvc.LocalService("workflow")
            wf_service.trg_validate(uid, self._name, 
                                    pt.id, 'cancel', cr)
        return True
    
    def move_paid(self, cr, uid, ids, *args):
        for move in self.browse(cr, uid, ids):
            if move.state in ['due']:
                self.write(cr, uid, [move.id], {'state': 'paid'})
        return True
    
    def move_set_due(self, cr, uid, ids, *args):
        for move in self.browse(cr, uid, ids):
            if move.state in ['paid']:
                self.write(cr, uid, [move.id], {'state': 'due'})
        return True
    
    def unlink(self, cr, uid, ids, context=None):
        # To avoid if move is linked to voucher
        for move in self.browse(cr, uid, ids):
            if move.wt_voucher_line_id \
                    and move.wt_voucher_line_id.voucher_line_id:
                raise orm.except_orm(_('Warning!'), 
                    _('You cannot delet move linked to voucher.\
                    You must before delete the voucher.'))
        
        return super(withholding_tax_move, self).unlink(cr, uid, ids, 
                                                        context=context)