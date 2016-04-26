# -*- encoding: utf-8 -*-
##############################################################################
#
#    SEPA Direct Debit module for Odoo
#    Copyright (C) 2013-2015 Akretion (http://www.akretion.com)
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


from openerp import models, fields, api, _
from openerp.exceptions import Warning
from openerp import workflow
from lxml import etree
import logging
import base64

logger = logging.getLogger(__name__)


class BankingExportSepaCbiWizard(models.TransientModel):
    _name = 'banking.export.sepa.cbi.wizard'
    _inherit = ['banking.export.pain']
    _description = 'Export SEPA CBI File'

    state = fields.Selection([
        ('create', 'Create'),
        ('finish', 'Finish'),
        ], string='State', readonly=True, default='create')
    batch_booking = fields.Boolean(
        string='Batch Booking',
        help="If true, the bank statement will display only one credit "
        "line for all the direct debits of the SEPA file ; if false, "
        "the bank statement will display one credit line per direct "
        "debit of the SEPA file.")
    charge_bearer = fields.Selection([
        ('SLEV', 'Following Service Level'),
        ('SHAR', 'Shared'),
        ('CRED', 'Borne by Creditor'),
        ('DEBT', 'Borne by Debtor'),
        ], string='Charge Bearer', required=True, default='SLEV',
        help="Following service level : transaction charges are to be "
        "applied following the rules agreed in the service level "
        "and/or scheme (SEPA Core messages must use this). Shared : "
        "transaction charges on the creditor side are to be borne "
        "by the creditor, transaction charges on the debtor side are "
        "to be borne by the debtor. Borne by creditor : all "
        "transaction charges are to be borne by the creditor. Borne "
        "by debtor : all transaction charges are to be borne by the debtor.")
    nb_transactions = fields.Integer(
        string='Number of Transactions', readonly=True)
    total_amount = fields.Float(string='Total Amount', readonly=True)
    file = fields.Binary(string="File", readonly=True)
    filename = fields.Char(string="Filename", readonly=True)
    payment_order_ids = fields.Many2many(
        'payment.order', 'wiz_sepa_cbi_payorders_rel', 'wizard_id',
        'payment_order_id', string='Payment Orders', readonly=True)

    @api.model
    def create(self, vals):
        payment_order_ids = self._context.get('active_ids', [])
        vals.update({
            'payment_order_ids': [[6, 0, payment_order_ids]],
        })
        return super(BankingExportSepaCbiWizard, self).create(vals)

    '''
    def _get_previous_bank(self, payline):
        previous_bank = False
        older_lines = self.env['payment.line'].search([
            ('mandate_id', '=', payline.mandate_id.id),
            ('bank_id', '!=', payline.bank_id.id)])
        if older_lines:
            previous_date = False
            previous_payline = False
            for older_line in older_lines:
                if hasattr(older_line.order_id, 'date_sent'):
                    older_line_date = older_line.order_id.date_sent
                else:
                    older_line_date = older_line.order_id.date_done
                if (older_line_date and
                        older_line_date > previous_date):
                    previous_date = older_line_date
                    previous_payline = older_line
            if previous_payline:
                previous_bank = previous_payline.bank_id
        return previous_bank
    '''
    """
    @api.model
    def finalize_sepa_file_creation(self, xml_root, total_amount,
                                    transactions_count, gen_args):
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
            self._prepare_export_sepa(total_amount,
                                      transactions_count,
                                      xml_string, gen_args)
            )

        self.file_id = file_id
        self.state = 'finish'

        action = {
            'name': 'SEPA File',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': self._name,
            #'res_model': 'banking.export.pain',
            'res_id': self.id,
            'target': 'new',
            }
        return action"""
    @api.multi
    def finalize_sepa_file_creation(
            self, xml_root, total_amount, transactions_count, gen_args):
        xml_string = etree.tostring(
            xml_root, pretty_print=True, encoding='UTF-8',
            xml_declaration=True)
        logger.debug(
            "Generated SEPA XML file in format %s below"
            % gen_args['pain_flavor'])
        logger.debug(xml_string)
        # finchè non capisco che errore è nel controllo con il  file xsd:
        # self._validate_xml(xml_string, gen_args)

        order_ref = []
        for order in self.payment_order_ids:
            if order.reference:
                order_ref.append(order.reference.replace('/', '-'))
        filename = '%s%s.xml' % (gen_args['file_prefix'], '-'.join(order_ref))

        self.write({
            'nb_transactions': transactions_count,
            'total_amount': total_amount,
            'filename': filename,
            'file': base64.encodestring(xml_string),
            'state': 'finish',
            })

        action = {
            'name': _('SEPA File'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form,tree',
            'res_model': self._name,
            'res_id': self.ids[0],
            'target': 'new',
        }
        return action

    @api.model
    def generate_initiating_party_block(self, parent_node, gen_args):
        '''
        CBI Extend for redifine CUC code and other datas
        '''
        # Change logic for initiating_party_identifier:
        # Now is CUC code in the partner bank of the company

        #my_company_name = self._prepare_field(
        #    'Company Name',
        #    'sepa_export.payment_order_ids[0].mode.bank_id.partner_id.name',
        #    {'sepa_export': gen_args['sepa_export']},
        #    gen_args.get('name_maxsize'), gen_args=gen_args, context=context)
        my_company_name = self._prepare_field(
            'Company Name',
            'self.payment_order_ids[0].mode.bank_id.partner_id.name',
            {'self': self}, gen_args.get('name_maxsize'), gen_args=gen_args)
        initiating_party_1_8 = etree.SubElement(parent_node, 'InitgPty')
        initiating_party_name = etree.SubElement(initiating_party_1_8, 'Nm')
        initiating_party_name.text = \
            self.payment_order_ids[0].mode.bank_id.partner_id.name
        #initiating_party_identifier = self.pool['res.company'].\
        #    _get_initiating_party_identifier(
        #        cr, uid,
        #        gen_args['sepa_export'].payment_order_ids[0].company_id.id,
        #        context=context)
        # if not gen_args['sepa_export'].payment_order_ids[0].mode.bank_id.cuc_code:
        if not self.payment_order_ids[0].mode.bank_id.cuc_code:
            raise orm.except_orm(
                _('Error:'),
                _("Missing CUC code int the company bank"))
        # initiating_party_identifier = gen_args['sepa_export'].\
        #     payment_order_ids[0].mode.bank_id.cuc_code
        initiating_party_identifier = \
            self.payment_order_ids[0].mode.bank_id.cuc_code
        # initiating_party_issuer = gen_args['sepa_export'].\
        #    payment_order_ids[0].company_id.initiating_party_issuer
        initiating_party_issuer = \
            self.payment_order_ids[0].company_id.initiating_party_issuer
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

    @api.model
    def generate_party_agent(self, parent_node, party_type, party_type_label,
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
        '''
        if party_type == 'Cdtr' and not iban[:2] == 'IT':
            res = super(banking_export_sepa_cbi_wizard, self).generate_party_agent(
                            parent_node, party_type, party_type_label, order,
                            party_name, iban, bic, eval_ctx, gen_args)'''
        return True

    @api.model
    def generate_creditor_scheme_identification(
            self, parent_node, identification, identification_label,
            eval_ctx, scheme_name_proprietary, gen_args):
        #
        # CBI logic modified for not try to add other info
        #
        '''
        csi_id = etree.SubElement(parent_node, 'Id')
        csi_privateid = etree.SubElement(csi_id, 'PrvtId')
        csi_other = etree.SubElement(csi_privateid, 'Othr')
        csi_other_id = etree.SubElement(csi_other, 'Id')
        csi_other_id.text = self._prepare_field(
            identification_label, identification, eval_ctx, gen_args=gen_args)
        csi_scheme_name = etree.SubElement(csi_other, 'SchmeNm')
        csi_scheme_name_proprietary = etree.SubElement(
            csi_scheme_name, 'Prtry')
        csi_scheme_name_proprietary.text = scheme_name_proprietary
        '''
        return True

    @api.multi
    def create_sepa(self):
        """Creates the SEPA Direct Debit file. That's the important code !"""
        sepa_export = self[0]
        pain_flavor = self.payment_order_ids[0].mode.type.code
        convert_to_ascii = \
            self.payment_order_ids[0].mode.convert_to_ascii
        if pain_flavor == 'pain.008.001.02':
            bic_xml_tag = 'BIC'
            name_maxsize = 70
            root_xml_tag = 'CstmrDrctDbtInitn'
        elif pain_flavor == 'CBIBdyPaymentRequest.00.04.00':
            bic_xml_tag = 'BIC'
            name_maxsize = 70
            root_xml_tag = 'CBIEnvelPaymentRequest'
        elif pain_flavor == 'pain.008.001.03':
            bic_xml_tag = 'BIC'
            name_maxsize = 70
            root_xml_tag = 'CstmrCdtTrfInitn'
        elif pain_flavor == 'pain.008.001.04':
            bic_xml_tag = 'BICFI'
            name_maxsize = 140
            root_xml_tag = 'CstmrDrctDbtInitn'
        else:
            raise Warning(
                _("Payment Type Code '%s' is not supported. The only "
                  "Payment Type Code supported for SEPA Direct Debit are "
                  "'pain.008.001.02', 'pain.008.001.03' and "
                  "'pain.008.001.04'.") % pain_flavor)
        gen_args = {
            'bic_xml_tag': bic_xml_tag,
            'name_maxsize': name_maxsize,
            'convert_to_ascii': convert_to_ascii,
            # 'payment_method': 'DD',
            'payment_method': 'TRF',
            'file_prefix': 'sdd_',
            'pain_flavor': pain_flavor,
            'pain_xsd_file': 'account_banking_sepa_cbi/data/%s.xsd' \
                % pain_flavor,
            # 'account_banking_sepa_direct_debit/data/%s.xsd' % pain_flavor,
            'sepa_export': sepa_export,
        }
        pain_ns = {
            'xsi': 'http://www.w3.org/2001/XMLSchema-instance',
            None: 'urn:CBI:xsd:%s' % pain_flavor,
        }
        # xml_root = etree.Element('Document', nsmap=pain_ns)
        xml_root = etree.Element('CBIBdyPaymentRequest', nsmap=pain_ns)
        pain_root = etree.SubElement(xml_root, root_xml_tag)
        # Add tag x cbi
        pain_root = etree.SubElement(pain_root, 'CBIPaymentRequest')
        pain_03_to_05 = \
            ['pain.001.001.03', 'pain.001.001.04', 'pain.001.001.05',
             'CBIBdyPaymentRequest.00.04.00']
        # A. Group header
        group_header_1_0, nb_of_transactions_1_6, control_sum_1_7 = \
            self.generate_group_header_block(pain_root, gen_args)
        transactions_count_1_6 = 0
        total_amount = 0.0
        amount_control_sum_1_7 = 0.0
        lines_per_group = {}
        # key = (requested_date, priority, sequence type)
        # value = list of lines as objects
        # Iterate on payment orders
        today = fields.Date.context_today(self)
        for payment_order in self.payment_order_ids:
            total_amount = total_amount + payment_order.total
            # Iterate each payment lines
            for line in payment_order.line_ids:
                transactions_count_1_6 += 1
                priority = line.priority
                if payment_order.date_prefered == 'due':
                    requested_date = line.ml_maturity_date or today
                elif payment_order.date_prefered == 'fixed':
                    requested_date = payment_order.date_scheduled or today
                else:
                    requested_date = today
                if not line.mandate_id:
                    raise Warning(
                        _("Missing SEPA Direct Debit mandate on the payment "
                          "line with partner '%s' and Invoice ref '%s'.")
                        % (line.partner_id.name,
                           line.ml_inv_ref.number))
                scheme = line.mandate_id.scheme
                if line.mandate_id.state != 'valid':
                    raise Warning(
                        _("The SEPA Direct Debit mandate with reference '%s' "
                          "for partner '%s' has expired.")
                        % (line.mandate_id.unique_mandate_reference,
                           line.mandate_id.partner_id.name))
                if line.mandate_id.type == 'oneoff':
                    seq_type = 'OOFF'
                    if line.mandate_id.last_debit_date:
                        raise Warning(
                            _("The mandate with reference '%s' for partner "
                              "'%s' has type set to 'One-Off' and it has a "
                              "last debit date set to '%s', so we can't use "
                              "it.")
                            % (line.mandate_id.unique_mandate_reference,
                               line.mandate_id.partner_id.name,
                               line.mandate_id.last_debit_date))
                elif line.mandate_id.type == 'recurrent':
                    seq_type_map = {
                        'recurring': 'RCUR',
                        'first': 'FRST',
                        'final': 'FNAL',
                    }
                    seq_type_label = \
                        line.mandate_id.recurrent_sequence_type
                    assert seq_type_label is not False
                    seq_type = seq_type_map[seq_type_label]
                key = (requested_date, priority, seq_type, scheme)
                if key in lines_per_group:
                    lines_per_group[key].append(line)
                else:
                    lines_per_group[key] = [line]
                # Write requested_exec_date on 'Payment date' of the pay line
                if requested_date != line.date:
                    line.date = requested_date

        for (requested_date, priority, sequence_type, scheme), lines in \
                lines_per_group.items():
            # B. Payment info
            payment_info_2_0, nb_of_transactions_2_4, control_sum_2_5 = \
                self.generate_start_payment_info_block(
                    pain_root,
                    "self.payment_order_ids[0].reference + '-' + "
                    "sequence_type + '-' + requested_date.replace('-', '')  "
                    "+ '-' + priority",
                    priority, scheme, sequence_type, requested_date, {
                        'self': self,
                        'sequence_type': sequence_type,
                        'priority': priority,
                        'requested_date': requested_date,
                    }, gen_args)

            self.generate_party_block(
                payment_info_2_0, 'Dbtr', 'B',
                'self.payment_order_ids[0].mode.bank_id.partner_id.'
                'name',
                'self.payment_order_ids[0].mode.bank_id.acc_number',
                'self.payment_order_ids[0].mode.bank_id.bank.bic or '
                'self.payment_order_ids[0].mode.bank_id.bank_bic',
                {'self': self}, gen_args)
            charge_bearer_2_24 = etree.SubElement(payment_info_2_0, 'ChrgBr')
            charge_bearer_2_24.text = self.charge_bearer
            """
            creditor_scheme_identification_2_27 = etree.SubElement(
                payment_info_2_0, 'CdtrSchmeId')
            self.generate_creditor_scheme_identification(
                creditor_scheme_identification_2_27,
                'self.payment_order_ids[0].company_id.'
                'sepa_creditor_identifier',
                'SEPA Creditor Identifier', {'self': self}, 'SEPA', gen_args)
            """
            transactions_count_2_4 = 0
            amount_control_sum_2_5 = 0.0
            for line in lines:
                #transactions_count_1_6 += 1
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
                    'End to End Identification', 'line.name',
                    {'line': line}, 35, gen_args=gen_args)
                currency_name = self._prepare_field(
                    'Currency Code', 'line.currency.name',
                    {'line': line}, 3, gen_args=gen_args)
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
                    credit_transfer_transaction_info_2_27, 'Cdtr', 'C',
                    'line.partner_id.name', 'line.bank_id.acc_number',
                    'line.bank_id.bank.bic', {'line': line}, gen_args)

                self.generate_remittance_info_block(
                    credit_transfer_transaction_info_2_27, line, gen_args)

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
        # >> v8
        # Remove the duplicate node  LclInstrm in payment
        CtrlSum_node = xml_root.xpath('//PmtInf//LclInstrm')[0] #CBI required
        CtrlSum_node.getparent().remove(CtrlSum_node) # You can remove node only from parent
        # Remove the duplicate node  CtrlSum in payment
        CtrlSum_node = xml_root.xpath('//PmtInf//SeqTp')[0] #CBI required
        CtrlSum_node.getparent().remove(CtrlSum_node) # You can remove node only from parent

        #print(etree.tostring(xml_root, pretty_print=True))
        return self.finalize_sepa_file_creation(
            xml_root, total_amount, transactions_count_1_6, gen_args)

    @api.multi
    def save_sepa(self):
        """Save the SEPA Direct Debit file: mark all payments in the file
        as 'sent'. Write 'last debit date' on mandate and set oneoff
        mandate to expired.
        """
        abmo = self.env['account.banking.mandate']
        for order in self.payment_order_ids:
            workflow.trg_validate(
                self._uid, 'payment.order', order.id, 'done', self._cr)
            self.env['ir.attachment'].create({
                'res_model': 'payment.order',
                'res_id': order.id,
                'name': self.filename,
                'datas': self.file,
                })
            to_expire_mandates = abmo.browse([])
            first_mandates = abmo.browse([])
            all_mandates = abmo.browse([])
            for line in order.line_ids:
                if line.mandate_id in all_mandates:
                    continue
                all_mandates += line.mandate_id
                if line.mandate_id.type == 'oneoff':
                    to_expire_mandates += line.mandate_id
                elif line.mandate_id.type == 'recurrent':
                    seq_type = line.mandate_id.recurrent_sequence_type
                    if seq_type == 'final':
                        to_expire_mandates += line.mandate_id
                    elif seq_type == 'first':
                        first_mandates += line.mandate_id
            all_mandates.write(
                {'last_debit_date': fields.Date.context_today(self)})
            to_expire_mandates.write({'state': 'expired'})
            first_mandates.write({
                'recurrent_sequence_type': 'recurring',
                'sepa_migrated': True,
                })
        return True
