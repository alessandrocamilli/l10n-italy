# -*- encoding: utf-8 -*-
##############################################################################
#
#    SEPA Credit Transfer module for OpenERP
#    Copyright (C) 2010-2013 Akretion (http://www.akretion.com)
#    @author: Alexis de Lattre <alexis.delattre@akretion.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU Affero General Public License as
#    published by the Free Software Foundation, either version 3 of the
#    License, or (at your option) any later version.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU Affero General Public License for more details.
#
#    You should have received a copy of the GNU Affero General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
##############################################################################


from openerp.osv import orm, fields
from openerp.tools.translate import _
from openerp import netsvc
from lxml import etree
import logging

logger = logging.getLogger(__name__)

class res_partner_bank(orm.Model):
    _inherit = 'res.partner.bank'
    _columns = {
        'cuc_code': fields.char('CUC Code')
    }

class banking_export_sepa_cbi_wizard(orm.TransientModel):
    _name = 'banking.export.sepa.cbi.wizard'
    _inherit = ['banking.export.pain']
    _description = 'Export SEPA CBI File'

    _columns = {
        'state': fields.selection([
            ('create', 'Create'),
            ('finish', 'Finish'),
            ], 'State', readonly=True),
        'batch_booking': fields.boolean(
            'Batch Booking',
            help="If true, the bank statement will display only one debit "
            "line for all the wire transfers of the SEPA XML file ; if "
            "false, the bank statement will display one debit line per wire "
            "transfer of the SEPA XML file."),
        'charge_bearer': fields.selection([
            ('SLEV', 'Following Service Level'),
            ('SHAR', 'Shared'),
            ('CRED', 'Borne by Creditor'),
            ('DEBT', 'Borne by Debtor'),
            ], 'Charge Bearer', required=True,
            help="Following service level : transaction charges are to be "
            "applied following the rules agreed in the service level and/or "
            "scheme (SEPA Core messages must use this). Shared : transaction "
            "charges on the debtor side are to be borne by the debtor, "
            "transaction charges on the creditor side are to be borne by "
            "the creditor. Borne by creditor : all transaction charges are "
            "to be borne by the creditor. Borne by debtor : all transaction "
            "charges are to be borne by the debtor."),
        'nb_transactions': fields.related(
            'file_id', 'nb_transactions', type='integer',
            string='Number of Transactions', readonly=True),
        'total_amount': fields.related(
            'file_id', 'total_amount', type='float', string='Total Amount',
            readonly=True),
        'file_id': fields.many2one(
            #'banking.export.sepa', 'SEPA XML File', readonly=True),
            'banking.export.sdd', 'SEPA XML File', readonly=True),
        'file': fields.related(
            'file_id', 'file', string="File", type='binary', readonly=True),
        'filename': fields.related(
            'file_id', 'filename', string="Filename", type='char',
            size=256, readonly=True),
        'payment_order_ids': fields.many2many(
            'payment.order', 'wiz_sepa_cbi_payorders_rel', 'wizard_id',
            'payment_order_id', 'Payment Orders', readonly=True),
        }

    _defaults = {
        'charge_bearer': 'SLEV',
        'state': 'create',
        }

    def create(self, cr, uid, vals, context=None):
        payment_order_ids = context.get('active_ids', [])
        vals.update({
            'payment_order_ids': [[6, 0, payment_order_ids]],
        })
        return super(banking_export_sepa_cbi_wizard, self).create(
            cr, uid, vals, context=context)
        
    def finalize_sepa_file_creation(
            self, cr, uid, ids, xml_root, total_amount, transactions_count,
            gen_args, context=None):
        ''' 
        Extended to avoid control xsd
        '''
        xml_string = etree.tostring(
            xml_root, pretty_print=True, encoding='UTF-8',
            xml_declaration=True)
        logger.debug(
            "Generated SEPA XML file in format %s below"
            % gen_args['pain_flavor'])
        logger.debug(xml_string)
        ## finchè non capisco che errore è nel controllo con il  file xsd:
        ## The XML document '/home/openforce/lp/openforce-addons/account_banking_sepa_cbi/data/CBIBdyPaymentRequest.00.04.00.xsd' is not a schema document.
        ###self._validate_xml(cr, uid, xml_string, gen_args, context=context)
        banking_export_sdd_obj = self.pool['banking.export.sdd']
        #file_id = gen_args['file_obj'].create(
        file_id = banking_export_sdd_obj.create(
            cr, uid, self._prepare_export_sepa(
                cr, uid, total_amount, transactions_count,
                xml_string, gen_args, context=context),
            context=context)
        self.write(
            cr, uid, ids, {
                'file_id': file_id,
                'state': 'finish',
            }, context=context)
        
        action = {
            'name': 'SEPA File',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': self._name,
            #'res_model': 'banking.export.pain',
            'res_id': ids[0],
            'target': 'new',
            }
        return action
    
    def generate_initiating_party_block(
            self, cr, uid, parent_node, gen_args, context=None):
        '''
        CBI Extend for redifine CUC code and other datas
        '''
        # Change logic for initiating_party_identifier:
        # Now is CUC code in the partner bank of the company
        my_company_name = self._prepare_field(
            cr, uid, 'Company Name',
            'sepa_export.payment_order_ids[0].mode.bank_id.partner_id.name',
            {'sepa_export': gen_args['sepa_export']},
            gen_args.get('name_maxsize'), gen_args=gen_args, context=context)
        initiating_party_1_8 = etree.SubElement(parent_node, 'InitgPty')
        initiating_party_name = etree.SubElement(initiating_party_1_8, 'Nm')
        initiating_party_name.text = my_company_name
        #initiating_party_identifier = self.pool['res.company'].\
        #    _get_initiating_party_identifier(
        #        cr, uid,
        #        gen_args['sepa_export'].payment_order_ids[0].company_id.id,
        #        context=context)
        if not gen_args['sepa_export'].payment_order_ids[0].mode.bank_id.cuc_code:
            raise orm.except_orm(
                _('Error:'),
                _("Missing CUC code int the company bank"))
        initiating_party_identifier = gen_args['sepa_export'].\
            payment_order_ids[0].mode.bank_id.cuc_code
        initiating_party_issuer = gen_args['sepa_export'].\
            payment_order_ids[0].company_id.initiating_party_issuer
        if initiating_party_identifier and initiating_party_issuer:
            iniparty_id = etree.SubElement(initiating_party_1_8, 'Id')
            iniparty_org_id = etree.SubElement(iniparty_id, 'OrgId')
            iniparty_org_other = etree.SubElement(iniparty_org_id, 'Othr')
            iniparty_org_other_id = etree.SubElement(iniparty_org_other, 'Id')
            iniparty_org_other_id.text = initiating_party_identifier
            iniparty_org_other_issuer = etree.SubElement(
                iniparty_org_other, 'Issr')
            iniparty_org_other_issuer.text = initiating_party_issuer
        return True
    
    def generate_party_agent(
            self, cr, uid, parent_node, party_type, party_type_label,
            order, party_name, iban, bic, eval_ctx, gen_args, context=None):
        
        #
        # CBI logic modified for add ABI of debitor 
        #
        # ABI code from IBAN
        if party_type == 'Dbtr':
            company_bank = gen_args['sepa_export'].payment_order_ids[0].mode.\
                                                                    bank_id
            if 'bank_abi' in company_bank:
                abi_code = company_bank.bank_abi
            # ... try from iban
            if not abi_code and company_bank.state == 'iban':
                iban = company_bank.acc_number.replace(" ","")
                abi_code = iban[5:10]
            if not abi_code:
                raise orm.except_orm(
                    _('Error:'),
                    _("Error Bank Code ABI"))
            
            party_agent = etree.SubElement(parent_node, '%sAgt' % party_type)
            party_agent_institution = etree.SubElement(
                party_agent, 'FinInstnId')
            party_agent_institution_sys = etree.SubElement(
                party_agent_institution, 'ClrSysMmbId')
            party_agent_institution_sys_abi = etree.SubElement(
                    party_agent_institution_sys, 'MmbId')
            party_agent_institution_sys_abi.text = abi_code
        #
        # In case of stranger partner, add FinInstnId tags
        #
        if party_type == 'Cdtr' and not iban[:2] == 'IT':
            res = super(banking_export_sepa_cbi_wizard, self).generate_party_agent(
                            cr, uid, parent_node, party_type, party_type_label,
                            order, party_name, iban, bic, eval_ctx, gen_args,
                            context=None)
        return True

    def create_sepa(self, cr, uid, ids, context=None):
        '''
        Creates the SEPA Credit Transfer file. That's the important code !
        '''
        if context is None:
            context = {}
        sepa_export = self.browse(cr, uid, ids[0], context=context)
        pain_flavor = sepa_export.payment_order_ids[0].mode.type.code
        convert_to_ascii = \
            sepa_export.payment_order_ids[0].mode.convert_to_ascii
        if pain_flavor == 'pain.001.001.02':
            bic_xml_tag = 'BIC'
            name_maxsize = 70
            root_xml_tag = 'pain.001.001.02'
        elif pain_flavor == 'pain.001.001.03':
            bic_xml_tag = 'BIC'
            # size 70 -> 140 for <Nm> with pain.001.001.03
            # BUT the European Payment Council, in the document
            # "SEPA Credit Transfer Scheme Customer-to-bank
            # Implementation guidelines" v6.0 available on
            # http://www.europeanpaymentscouncil.eu/knowledge_bank.cfm
            # says that 'Nm' should be limited to 70
            # so we follow the "European Payment Council"
            # and we put 70 and not 140
            name_maxsize = 70
            root_xml_tag = 'CstmrCdtTrfInitn'
        elif pain_flavor == 'CBIBdyPaymentRequest.00.04.00':
            bic_xml_tag = 'BIC'
            name_maxsize = 70
            root_xml_tag = 'CBIEnvelPaymentRequest'
        elif pain_flavor == 'pain.001.001.04':
            bic_xml_tag = 'BICFI'
            name_maxsize = 140
            root_xml_tag = 'CstmrCdtTrfInitn'
        elif pain_flavor == 'pain.001.001.05':
            bic_xml_tag = 'BICFI'
            name_maxsize = 140
            root_xml_tag = 'CstmrCdtTrfInitn'

        else:
            raise orm.except_orm(
                _('Error:'),
                _("Payment Type Code '%s' is not supported. The only "
                    "Payment Type Codes supported for SEPA Credit Transfers "
                    "are 'pain.001.001.02', 'pain.001.001.03', "
                    "'pain.001.001.04','pain.001.001.05' and CBIBdyPaymentRequest.00.04.00.")
                % pain_flavor)

        gen_args = {
            'bic_xml_tag': bic_xml_tag,
            'name_maxsize': name_maxsize,
            'convert_to_ascii': convert_to_ascii,
            'payment_method': 'TRF',
            'pain_flavor': pain_flavor,
            'sepa_export': sepa_export,
            # v8 'file_obj': self.pool['banking.export.sepa'],
            'file_prefix': 'cbi_',
            'pain_xsd_file':
            #'account_banking_sepa_credit_transfer/data/%s.xsd'
            'account_banking_sepa_cbi/data/%s.xsd'
            % pain_flavor,
        }
        pain_ns = {
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            None: 'urn:CBI:xsd:%s' % pain_flavor,
            }
        #xml_root = etree.Element('Document', nsmap=pain_ns)
        xml_root = etree.Element('CBIBdyPaymentRequest', nsmap=pain_ns)
        
        pain_root = etree.SubElement(xml_root, root_xml_tag)
        # Add tag x cbi
        pain_root = etree.SubElement(pain_root, 'CBIPaymentRequest')
        pain_03_to_05 = \
            ['pain.001.001.03', 'pain.001.001.04', 'pain.001.001.05', 
             'CBIBdyPaymentRequest.00.04.00']
            
        # A. Group header
        group_header_1_0, nb_of_transactions_1_6, control_sum_1_7 = \
            self.generate_group_header_block(
                cr, uid, pain_root, gen_args, context=context)
            
        transactions_count_1_6 = 0
        total_amount = 0.0
        amount_control_sum_1_7 = 0.0
        lines_per_group = {}
        
        # key = (requested_date, priority)
        # values = list of lines as object
        today = fields.date.context_today(self, cr, uid, context=context)
        for payment_order in sepa_export.payment_order_ids:
            total_amount = total_amount + payment_order.total
            for line in payment_order.line_ids:
                priority = line.priority
                if payment_order.date_prefered == 'due':
                    requested_date = line.ml_maturity_date or today
                elif payment_order.date_prefered == 'fixed':
                    requested_date = payment_order.date_scheduled or today
                else:
                    requested_date = today
                key = (requested_date, priority)
                if key in lines_per_group:
                    lines_per_group[key].append(line)
                else:
                    lines_per_group[key] = [line]
                # Write requested_date on 'Payment date' of the pay line
                if requested_date != line.date:
                    self.pool['payment.line'].write(
                        cr, uid, line.id,
                        {'date': requested_date}, context=context)

        for (requested_date, priority), lines in lines_per_group.items():
            # B. Payment info
            payment_info_2_0, nb_of_transactions_2_4, control_sum_2_5 = \
                self.generate_start_payment_info_block(
                    cr, uid, pain_root,
                    "sepa_export.payment_order_ids[0].reference + '-' "
                    "+ requested_date.replace('-', '')  + '-' + priority",
                    priority, False, False, requested_date, {
                        'sepa_export': sepa_export,
                        'priority': priority,
                        'requested_date': requested_date,
                    }, gen_args, context=context)

            self.generate_party_block(
                cr, uid, payment_info_2_0, 'Dbtr', 'B',
                'sepa_export.payment_order_ids[0].mode.bank_id.partner_id.'
                'name',
                'sepa_export.payment_order_ids[0].mode.bank_id.acc_number',
                'sepa_export.payment_order_ids[0].mode.bank_id.bank.bic',
                {'sepa_export': sepa_export},
                gen_args, context=context)

            charge_bearer_2_24 = etree.SubElement(payment_info_2_0, 'ChrgBr')
            charge_bearer_2_24.text = sepa_export.charge_bearer

            transactions_count_2_4 = 0
            amount_control_sum_2_5 = 0.0
            for line in lines:
                transactions_count_1_6 += 1
                transactions_count_2_4 += 1
                # C. Credit Transfer Transaction Info
                credit_transfer_transaction_info_2_27 = etree.SubElement(
                    payment_info_2_0, 'CdtTrfTxInf')
                payment_identification_2_28 = etree.SubElement(
                    credit_transfer_transaction_info_2_27, 'PmtId')
                # CBI PmtTpInf (Causale bonifici)
                payment_identification_2_28_PmtTpInf = etree.SubElement(
                    credit_transfer_transaction_info_2_27, 'PmtTpInf')
                payment_identification_2_28_CtgyPurp = etree.SubElement(
                    payment_identification_2_28_PmtTpInf, 'CtgyPurp')
                payment_identification_2_28_CtgyPurp_Cd = etree.SubElement(
                    payment_identification_2_28_CtgyPurp, 'Cd')
                payment_identification_2_28_CtgyPurp_Cd.text = 'SUPP' # generico 
                
                # CBI tag InstrId
                end2end_identification_2_30_InstrId = etree.SubElement(
                    payment_identification_2_28, 'InstrId')
                end2end_identification_2_30_InstrId.text = line.name
                
                end2end_identification_2_30 = etree.SubElement(
                    payment_identification_2_28, 'EndToEndId')
                end2end_identification_2_30.text = self._prepare_field(
                    cr, uid, 'End to End Identification', 'line.name',
                    {'line': line}, 35, gen_args=gen_args,
                    context=context)
                currency_name = self._prepare_field(
                    cr, uid, 'Currency Code', 'line.currency.name',
                    {'line': line}, 3, gen_args=gen_args,
                    context=context)
                amount_2_42 = etree.SubElement(
                    credit_transfer_transaction_info_2_27, 'Amt')
                instructed_amount_2_43 = etree.SubElement(
                    amount_2_42, 'InstdAmt', Ccy=currency_name)
                instructed_amount_2_43.text = '%.2f' % line.amount_currency
                amount_control_sum_1_7 += line.amount_currency
                amount_control_sum_2_5 += line.amount_currency

                if not line.bank_id:
                    raise orm.except_orm(
                        _('Error:'),
                        _("Missing Bank Account on invoice '%s' (payment "
                            "order line reference '%s').")
                        % (line.ml_inv_ref.number, line.name))
                self.generate_party_block(
                    cr, uid, credit_transfer_transaction_info_2_27, 'Cdtr',
                    'C', 'line.partner_id.name', 'line.bank_id.acc_number',
                    'line.bank_id.bank.bic', {'line': line}, gen_args,
                    context=context)

                self.generate_remittance_info_block(
                    cr, uid, credit_transfer_transaction_info_2_27,
                    line, gen_args, context=context)

            if pain_flavor in pain_03_to_05:
                nb_of_transactions_2_4.text = str(transactions_count_2_4)
                control_sum_2_5.text = '%.2f' % amount_control_sum_2_5

        if pain_flavor in pain_03_to_05:
            nb_of_transactions_1_6.text = str(transactions_count_1_6)
            control_sum_1_7.text = '%.2f' % amount_control_sum_1_7
        else:
            nb_of_transactions_1_6.text = str(transactions_count_1_6)
            control_sum_1_7.text = '%.2f' % amount_control_sum_1_7
            
        #
        # CBI required
        #
        # Add pain to group header tag
        GrpHdr_node = xml_root.xpath('//GrpHdr')[0] #CBI required
        GrpHdr_node.attrib['xmlns'] = 'urn:CBI:xsd:CBIPaymentRequest.00.04.00' #CBI required
        # Add pain to payment info tag
        PmtInf_node = xml_root.xpath('//PmtInf')[0] #CBI required
        PmtInf_node.attrib['xmlns'] = 'urn:CBI:xsd:CBIPaymentRequest.00.04.00' #CBI required
        # Remove the duplicate node  NbOfTxs in payment
        NbOfTxs_node = xml_root.xpath('//PmtInf//NbOfTxs')[0] #CBI required
        NbOfTxs_node.getparent().remove(NbOfTxs_node) # You can remove node only from parent
        # Remove the duplicate node  CtrlSum in payment
        CtrlSum_node = xml_root.xpath('//PmtInf//CtrlSum')[0] #CBI required
        CtrlSum_node.getparent().remove(CtrlSum_node) # You can remove node only from parent
        
        #print(etree.tostring(xml_root, pretty_print=True))
        
        return self.finalize_sepa_file_creation(
            cr, uid, ids, xml_root, total_amount, transactions_count_1_6,
            gen_args, context=context)

    def cancel_sepa(self, cr, uid, ids, context=None):
        '''
        Cancel the SEPA file: just drop the file
        '''
        sepa_export = self.browse(cr, uid, ids[0], context=context)
        self.pool.get('banking.export.sepa').unlink(
            cr, uid, sepa_export.file_id.id, context=context)
        return {'type': 'ir.actions.act_window_close'}

    def save_sepa(self, cr, uid, ids, context=None):
        '''
        Save the SEPA file: send the done signal to all payment
        orders in the file. With the default workflow, they will
        transition to 'done', while with the advanced workflow in
        account_banking_payment they will transition to 'sent' waiting
        reconciliation.
        '''
        sepa_export = self.browse(cr, uid, ids[0], context=context)
        self.pool.get('banking.export.sepa').write(
            cr, uid, sepa_export.file_id.id, {'state': 'sent'},
            context=context)
        wf_service = netsvc.LocalService('workflow')
        for order in sepa_export.payment_order_ids:
            wf_service.trg_validate(uid, 'payment.order', order.id, 'done', cr)
        return {'type': 'ir.actions.act_window_close'}
