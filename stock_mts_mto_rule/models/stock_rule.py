# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl).

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError
from odoo.tools import float_compare, float_is_zero
from openerp.exceptions import except_orm, Warning, RedirectWarning

class StockRule(models.Model):
	_inherit = 'stock.rule'

	action = fields.Selection(
		selection_add=[('split_procurement', 'Choose between MTS and MTO')])
	mts_rule_id = fields.Many2one(
		'stock.rule', string="MTS Rule")
	mto_rule_id = fields.Many2one(
		'stock.rule', string="MTO Rule")

	@api.constrains('action', 'mts_rule_id', 'mto_rule_id')
	def _check_mts_mto_rule(self):
		for rule in self:
			if rule.action == 'split_procurement':
				if not rule.mts_rule_id or not rule.mto_rule_id:
					msg = _('No MTS or MTO rule configured on procurement '
							'rule: %s!') % (rule.name, )
					raise ValidationError(msg)
				if (rule.mts_rule_id.location_src_id.id !=
						rule.mto_rule_id.location_src_id.id):
					msg = _('Inconsistency between the source locations of '
							'the mts and mto rules linked to the procurement '
							'rule: %s! It should be the same.') % (rule.name,)
					raise ValidationError(msg)

	def get_mto_qty_to_order(self, product, product_qty, product_uom, values):
		self.ensure_one()
		precision = self.env['decimal.precision']\
			.precision_get('Product Unit of Measure')
		src_location_id = self.mts_rule_id.location_src_id.id
		product_location = product.with_context(location=src_location_id)
		virtual_available = product_location.virtual_available
		qty_available = product.uom_id._compute_quantity(
			virtual_available, product_uom)
		if float_compare(qty_available, 0.0, precision_digits=precision) > 0:
			if float_compare(qty_available, product_qty,
							 precision_digits=precision) >= 0:
				return 0.0
			else:
				return product_qty - qty_available
		return product_qty
	
	def change_procurement_product_qty(self, procurements, qty):
		new_list = []
		new_procurements = procurements[0][0]
		new_procurements = new_procurements._replace(product_qty=qty)
		tuple = (new_procurements, procurements[0][1])
		new_list.append(tuple)
		return new_list
		
	
	def _run_split_procurement(self, procurements):
		procurement = procurements[0][0]
		product_id = procurement.product_id
		product_qty = procurement.product_qty
		product_uom = procurement.product_uom
		
		values = procurement.values
		self = procurements[0][1]
		
		precision = self.env['decimal.precision']\
			.precision_get('Product Unit of Measure')
		needed_qty = self.get_mto_qty_to_order(product_id, product_qty,
											   product_uom, values)
		
		mts_qty = product_qty - needed_qty
		
		mts_procurement = self.change_procurement_product_qty(procurements, mts_qty)
		mto_procurement = self.change_procurement_product_qty(procurements, needed_qty)
		
		if float_is_zero(needed_qty, precision_digits=precision):
			getattr(self.mts_rule_id, '_run_%s' % self.mts_rule_id.action)(procurements)
			
		elif float_compare(needed_qty, product_qty, precision_digits=precision) == 0.0:
			getattr(self.mto_rule_id, '_run_%s' % self.mto_rule_id.action)(procurements)
		
		else:
			getattr(self.mts_rule_id, '_run_%s' % self.mts_rule_id.action)(mts_procurement)
			getattr(self.mto_rule_id, '_run_%s' % self.mto_rule_id.action)(mto_procurement)
		return True
