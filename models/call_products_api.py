from odoo import models, fields, api
import requests, ast, re, logging

_logger = logging.getLogger(__name__)

class CallProductsApi(models.Model):
    _name = 'call.products.api'

    api_credentials_ids = fields.Many2one('api.credentials',string='Supplier')
    category_api_ids =  fields.Many2one('product.category.api', string='Category')
    subcategory_api_ids =  fields.Many2one('product.subcategory.api', string='Sub Category')
    brand_api_ids = fields.Many2one('product.brands.api', string='Brand')
    id_category = fields.Char(string='Category', readonly=True, default='0')
    id_subcategory = fields.Char(string='Category', readonly=True)
    keyword = fields.Char(string='Search for word')

    product_ids = fields.One2many('product.api.result', 'product_api_id', string='Products')

    # Método para asegurar que solo hay un registro
    @api.model
    def create(self, vals):
        existing_record = self.search([], limit=1)
        if existing_record:
            existing_record.write(vals)
            return existing_record
        return super(CallProductsApi, self).create(vals)

    @api.onchange('category_api_ids')
    def _onchange_category_api_ids(self):
        if self.category_api_ids:
            id_categoria = self.category_api_ids.codigo_categoria
            record = self.search([], limit=1)
            if record:
                record.write({'id_category': id_categoria,
                              'category_api_ids': self.category_api_ids
                              })
            configuration = self.env['api.configuration'].search([('name', '=', 'VerSubCategoria')], limit=1)
            if configuration:
                configuration.write({})

    @api.onchange('subcategory_api_ids')
    def _onchange_subcategory_api_ids(self):
        if self.subcategory_api_ids:
            id_subcategoria = self.subcategory_api_ids.codigo_sub_categoria
            record = self.search([], limit=1)
            if record:
                record.write({'id_subcategory': id_subcategoria})
        else:
            # Asigna '' si no hay subcategoría seleccionada
            record = self.search([], limit=1)
            if record:
                record.write({'id_subcategory': ''})

    def ejecutar_verCatalogo(self):
        api_credentials = self.api_credentials_ids
        # Consultar el proveedor para construir el header a traver del metodo write
        if api_credentials.name == 'MPS':
            configuration = self.env['api.configuration'].search([('name', '=', 'VerCatalogo')], limit=1)
            if configuration:
                configuration.write({})
        if api_credentials.name == 'INGRAM':
            configurationINGRAM = self.env['api.configuration'].search([('name', '=', 'Search Product')], limit=1)
            if configurationINGRAM:
                configurationINGRAM.write({})

    def create_products(self):
        product_api_results = self.env['product.api.result'].search([])
        for product in product_api_results:
            product.create_odoo_product()

    def call_delete_products_from_api_methods(self):
        # Buscar un registro en api.methods
        api_methods_record = self.env['api.methods'].search([], limit=1)
        if api_methods_record:
            api_methods_record.delete_products()
        else:
            _logger.warning('No se encontró ningún registro en api.methods para ejecutar delete_products.')

