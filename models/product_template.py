from odoo import models, fields
from odoo.fields import One2many


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    is_dropshipping = fields.Boolean(default=False, string='¿Dropshipping?')
    special_price = fields.Boolean (default=False, string='¿Special_price Price Dropshipping?')

    '''Información de pedido MPS'''
    dropshipping_warehouse = fields.Char (string="Dropshipping Warehouse")
    dropshipping_brand = fields.Char (string ='Product Brand')  # Relación inversa

    def cron_update_dropshipping_stock_info(self):
        '''Actualiza la información de los productos que se tienen
        en inventario, asociado a cada proveedor DROPSHIPPING'''
        # Buscar productos dropshipping
        dropshipping_products = self.env['product.template'].search([
            ('is_dropshipping', '=', True),
            ('special_price', '=', False)
        ])
        # Obtener la configuración de la API
        configuration_id = self.env['api.configuration'].search([('name', '=', 'ActualizarCatalogo(CASTOR)')])
        # Iterar sobre los productos dropshipping
        for product in dropshipping_products:
            if product.default_code:  # Asegurarse de que el producto tiene un default_code
                configuration_id.mps_methods_ids.authenticate_api(product.default_code)
        # Procesar todos los productos obtenidos
        product_api_records = self.env['call.products.api'].search([])
        if product_api_records:
            # Iterar sobre los registros y crear los productos
            for product_api_record in product_api_records:
                product_api_record.create_products()

class ProductSupplierInfo(models.Model):
    _inherit = 'product.supplierinfo'

    quantity_supplier = fields.Integer(string='Quantity supplier')