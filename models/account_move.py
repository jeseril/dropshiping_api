from odoo import models,exceptions
import logging
_logger = logging.getLogger(__name__)


class SaleOrder(models.Model):
    _inherit = 'account.move'

    def post(self):
        # Asegúrate de que existe un producto vinculado y que tiene el campo is_dropshipping
        for order in self:
            if order.line_ids.sale_line_ids.order_id.order_line.purchase_line_ids.order_id.api_supplier_order:
                raise exceptions.UserError("Ya existe una orden de compra de dropshipping para este pedido.")
            if not order.line_ids.sale_line_ids.order_id.order_line.purchase_line_ids.order_id.api_supplier_order:
                if any(line.product_id.product_tmpl_id.is_dropshipping for line in order.invoice_line_ids):
                    # Obtener los proveedores vinculados en las líneas del account_move
                    suppliers = order.invoice_line_ids.mapped(lambda line: line.product_id.product_tmpl_id.variant_seller_ids.partner_id)

                    if suppliers:
                        for supplier in suppliers:
                            # Buscar las credenciales de la API para el proveedor actual
                            api_credentials = self.env['api.credentials'].search([('partner_id', '=', supplier.id)], limit=1)

                            if api_credentials and supplier == api_credentials.partner_id:
                                # Buscar la configuración para realizar el pedido
                                configuration_id = self.env['api.configuration'].search([('name', '=', 'RealizarPedido')], limit=1)

                                if configuration_id:
                                    # Llamar al método de autenticación con el account_move
                                    configuration_id.mps_methods_ids.authenticate_api(account_move=order)

                        # Si llega aquí, significa que se han procesado todos los proveedores encontrados.
                        _logger.info(f'Se han procesado {len(suppliers)} proveedores para dropshipping.')
                    else:
                        raise exceptions.UserError("No se encontraron proveedores vinculados para los productos de dropshipping.")





