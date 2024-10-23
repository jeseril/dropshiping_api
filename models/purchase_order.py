from odoo import models,fields


class ProductTemplate(models.Model):
    _inherit = 'purchase.order'

    api_supplier_order = fields.Char(string='Supplier Order', editable=False)