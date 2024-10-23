from odoo import models, fields, api
import requests, ast, re, logging, json
from odoo.exceptions import UserError


_logger = logging.getLogger(__name__)


class MPSMethods(models.Model):
    _name = 'api.methods'

    api_configuration_id = fields.Many2one('api.configuration', string='API Configuration', readonly=True)

    def construct_header_or_params(self, api_configuration_id, text, sku=None, account_move=None):
        product_api_record = self.env['call.products.api'].search([], limit=1)
        pattern = r'@(.*?)@'

        def replace_products():
            # Productos relacionados en account_move
            if account_move:
                products_dict = {}
                for line in account_move.invoice_line_ids:
                    product_tmpl_id = line.product_id.product_tmpl_id

                    if product_tmpl_id.is_dropshipping:
                        if product_tmpl_id not in products_dict:
                            products_dict[product_tmpl_id] = {
                                'sku_producto': str(product_tmpl_id.default_code or ''),
                                'marca_producto': str(product_tmpl_id.dropshipping_brand or ''),
                                'bodega_producto': str(product_tmpl_id.dropshipping_warehouse or ''),
                                'cantidad': line.quantity
                            }
                        else:
                            products_dict[product_tmpl_id]['cantidad'] += line.quantity

                # Construir lista de detalles del pedido
                listaPedidoDetalle = []
                for product_info in products_dict.values():
                    listaPedidoDetalle.append({
                        "PartNum": product_info['sku_producto'],
                        "Cantidad": product_info['cantidad'],
                        "Marks": product_info['marca_producto'],
                        "Bodega": product_info['bodega_producto'],
                    })

                # Intentar convertir el string JSON a un diccionario
                try:
                    data = json.loads(text)
                    # Reemplazar la lista de detalles en el diccionario
                    if "listaPedido" in data and len(data["listaPedido"]) > 0:
                        data["listaPedido"][0]["listaPedidoDetalle"] = listaPedidoDetalle
                    # Convertir de nuevo a JSON el texto modificado
                    return json.dumps(data)
                except json.JSONDecodeError as e:
                    _logger.error(f"Error decoding JSON: {e}")
                    return text

        if account_move:
            text = replace_products()

        def replace_token(match):
            word_to_replace = match.group(1)
            # Reemplazo de token dinámico basado en el valor encontrado
            if word_to_replace == 'token':
                return api_configuration_id.api_credentials_id.token or ''
            if word_to_replace == 'type':
                return api_configuration_id.authorization_type or ''
            if word_to_replace == 'id_categoria':
                if product_api_record:
                    id_category = product_api_record.id_category
                    if isinstance(id_category, int):
                        id_category = str(id_category)
                    return id_category or ''
            if word_to_replace == 'id_subcategoria':
                if product_api_record:
                    id_subcategory = product_api_record.subcategory_api_ids.codigo_sub_categoria
                    if isinstance(id_subcategory, int):
                        id_subcategory = str(id_subcategory)
                    return id_subcategory or ''
            if word_to_replace == 'keyword':
                if product_api_record:
                    keyword = product_api_record.keyword
                    return keyword or ''
            if word_to_replace == 'sku':
                if product_api_record:
                    keyword = sku
                    return keyword or ''
            if word_to_replace == 'id_marca':
                if product_api_record:
                    id_brand = product_api_record.brand_api_ids.codigo_marca
                    if isinstance(id_brand, int):
                        id_brand = str(id_brand)
                    return id_brand or ''

            # Campos relacionados a account_move
            if account_move:
                if word_to_replace == 'numero_identificacion':
                    return str(account_move.partner_id.vat or '')
                if word_to_replace == 'nombre_cliente':
                    return str(account_move.partner_id.name or '')
                if word_to_replace == 'telefono_entrega':
                    return str(account_move.partner_id.phone or '')
                if word_to_replace == 'direccion':
                    return str(account_move.partner_id.street or '')
                if word_to_replace == 'departamento':
                    return str(account_move.partner_id.state_id.l10n_co_edi_code or '')
                if word_to_replace == 'ciudad':
                    ciudad_code = str(account_move.partner_id.city_id.l10n_co_edi_code or '')
                    departamento_code = str(account_move.partner_id.state_id.l10n_co_edi_code or '')
                    if ciudad_code.startswith(departamento_code):
                        ciudad_code = ciudad_code[len(departamento_code):]
                    return ciudad_code

            return match.group(0)  # Si no se encuentra reemplazo, devuelve el texto original

        # Reemplazar tokens en el texto
        replaced_text = re.sub(pattern, replace_token, text)

        # Intentar convertir el texto reemplazado a un diccionario
        try:
            result_dict = ast.literal_eval(replaced_text)
        except json.JSONDecodeError as e:
            _logger.error(f"Error al convertir texto a JSON: {e}")
            result_dict = {}

        return result_dict

    def authenticate_api(self,sku=None,account_move=None):
        url = self.api_configuration_id.url_endpoint

        http_method = self.api_configuration_id.http_method or ''
        headers = self.construct_header_or_params(self.api_configuration_id, self.api_configuration_id.headers or '{}', sku, account_move)
        params = self.construct_header_or_params(self.api_configuration_id, self.api_configuration_id.params or '{}', sku, account_move)
        data = self.construct_header_or_params(self.api_configuration_id, self.api_configuration_id.body or '{}', sku, account_move)
        # data = ast.literal_eval(self.api_configuration_id.body) if self.api_configuration_id.body else {}

        try:
            # Enviar solicitud en función del método HTTP
            if self.api_configuration_id.body_is_json:
                # Enviar como JSON
                response = getattr(requests, http_method)(url, headers=headers, json=data, params=params)
            else:
                # Enviar como form-data
                response = getattr(requests, http_method)(url, headers=headers, data=data, params=params)

            response.raise_for_status()  # Verifica si hubo un error HTTP

            if response.status_code == 200:
                json_response = response.json()
                if self.api_configuration_id.name == 'Token':
                    token = json_response.get('access_token')
                    self.api_configuration_id.api_credentials_id.write({'token': token})
                    _logger.info('Token actualizado correctamente.')

                # MPS
                elif self.api_configuration_id.name == 'VerCategoria':
                    self.fetch_categories_from_api(json_response)
                elif self.api_configuration_id.name == 'VerSubCategoria':
                    self.fetch_sub_categories_from_api(json_response)
                elif self.api_configuration_id.name in ['VerCatalogo', 'Search Product', 'ActualizarCatalogo(CASTOR)']:
                    self.fetch_products_from_api(json_response)
                elif self.api_configuration_id.name == 'VerMarcas':
                    self.fetch_brands_from_api(json_response)
                elif self.api_configuration_id.name == 'RealizarPedido':
                    self.fetch_purchase_order_api(json_response,account_move)
                # INGRAM

            else:
                error_message = 'Error de autenticación: {}'.format(response.text)
                raise ValueError(error_message)
        except requests.exceptions.RequestException as e:
            error_message = 'Error de conexión: {}'.format(e)
            raise ValueError(error_message)

    def fetch_categories_from_api(self, json_response):
        categories_data = json_response

        created_categories = []
        ProductCategory = self.env['product.category.api']  # Referencia al modelo product.category

        for category in categories_data:
            # Buscar la categoría existente usando el modelo correcto
            existing_category = ProductCategory.search([('codigo_categoria', '=', category['CodigoCategoria'])], limit=1)
            if not existing_category:
                # Crear la categoría en el modelo product.category
                created_category = ProductCategory.create({
                    'name': category['Categoria'],
                    'codigo_categoria': category['CodigoCategoria'],
                    'slug': category['slugcategory'],
                })
                created_categories.append(created_category)
                _logger.info('Categoría creada: %s', category['Categoria'])
            else:
                _logger.info('Categoría ya existe: %s', category['Categoria'])

        return created_categories

    def fetch_sub_categories_from_api(self,json_response):
        try:
            # Obtener el entorno de modelos de Odoo
            ProductSubcategories = self.env['product.subcategory.api']

            # Buscar subcategorías existentes
            existing_sub_categories = ProductSubcategories.search([])

            # Crear un diccionario de subcategorías existentes por código
            existing_sub_categories_by_code = {
                sub_category.codigo_sub_categoria: sub_category
                for sub_category in existing_sub_categories
            }

            created_or_updated_sub_categories = []

            for category in json_response:
                codigo_sub_categoria = category['CodigoSubCategoria']
                if codigo_sub_categoria in existing_sub_categories_by_code:
                    # Actualizar subcategoría existente
                    existing_sub_categories_by_code[codigo_sub_categoria].write({
                        'codigo_categoria': category['CodigoCategoria'],
                        'name': category['SubCatego'],
                        'slug': category['slugsubcat'],
                    })
                    created_or_updated_sub_categories.append(
                        existing_sub_categories_by_code[codigo_sub_categoria]
                    )
                else:
                    # Crear nueva subcategoría
                    created_category = ProductSubcategories.create({
                        'codigo_categoria': category['CodigoCategoria'],
                        'codigo_sub_categoria': codigo_sub_categoria,
                        'name': category['SubCatego'],
                        'slug': category['slugsubcat'],
                    })
                    created_or_updated_sub_categories.append(created_category)

            # Eliminar subcategorías no presentes en la respuesta de la API
            for sub_category in existing_sub_categories:
                if sub_category not in created_or_updated_sub_categories:
                    sub_category.unlink()

            return created_or_updated_sub_categories

        except requests.exceptions.RequestException as e:
            raise ValueError(f'Error fetching subcategories from API: {e}')

    def fetch_products_from_api(self, json_response):
        '''IDENTIFICA SI VIENE DE LA API O DE CASTOR'''
        if self.api_configuration_id.name in ['VerCatalogo', 'Search Product']:
            self.delete_products()

        try:
            # Detectar la estructura del JSON
            if 'listaproductos' in json_response:
                products = json_response.get('listaproductos', [])
            elif 'catalog' in json_response:
                products = json_response.get('catalog', [])
            else:
                raise ValueError("JSON response structure not recognized")

            _logger.info('Products received from API: %s', products)

            api_record = self.env['call.products.api'].search([], limit=1)
            product_api_id = api_record.id if api_record else False

            for product in products:
                if 'Sku' in product:  # MPS
                    for bodega in product.get('ListaProductosBodega', []):
                        self.env['product.api.result'].create({
                            'sku': product['Sku'],
                            'partnum': product['PartNum'],
                            'name': product['Name'],
                            'price': product['precio'],
                            'quantity': bodega.get('Cantidad', 0),
                            'mark': product['Marks'],
                            'warehouse': bodega.get('NombreBodega', ''),
                            'product_api_id': product_api_id
                        })
                elif 'ingramPartNumber' in product:  # INGRAM
                    self.env['product.api.result'].create({
                        'sku': product['ingramPartNumber'],
                        'partnum': product['vendorPartNumber'],
                        'name': product['description'],
                        'price': 0,  # Si hay un campo de precio en el nuevo JSON, cámbialo aquí
                        'quantity': 0,  # Igualmente, ajusta esto si hay información de cantidad
                        'mark': product['vendorName'],
                        'warehouse': '',  # Ajusta si hay información del almacén
                        'product_api_id': product_api_id
                    })

        except requests.exceptions.RequestException as e:
            error_message = 'Error fetching products: {}'.format(e)
            _logger.error(error_message)
            raise ValueError(error_message)

    def fetch_brands_from_api(self, json_response):
        brand_data = json_response

        ProductBrand = self.env['product.brands.api']  # Referencia al modelo product.category

        for brand in brand_data:

            existing_brand = self.env['product.brands.api'].search([('codigo_marca', '=', brand.get('CodigoMarca'))])

            if not existing_brand:
                # Si la marca no existe, se crea un nuevo registro
                self.env['product.brands.api'].create({
                    'codigo_marca': brand.get('CodigoMarca'),
                    'name': brand.get('Marks'),
                    'codigo_categoria': brand.get('CodigoCategoria'),
                    'marca_homologada': brand.get('MarcaHomologada'),
                })
            else:
                # Si la marca ya existe, se puede actualizar o ignorar según tus necesidades
                existing_brand.write({
                    'name': brand.get('Marks'),
                    'codigo_categoria': brand.get('CodigoCategoria'),
                    'marca_homologada': brand.get('MarcaHomologada'),
                })

    def fetch_purchase_order_api(self, json_response, account_move=None):
        try:
            order_data = json_response

            # Verificar si account_move está definido
            if account_move:
                # Buscar el registro de 'purchase.order' relacionado
                # Asumiendo que account_move.line_ids.sale_line_ids está vinculado a un pedido de compra
                purchase_line_ids = account_move.line_ids.mapped(
                    'sale_line_ids.order_id.order_line.purchase_line_ids.id'
                )
                purchase_orders = self.env['purchase.order'].search([
                    ('order_line.product_id.product_tmpl_id.is_dropshipping', '=', True),
                    ('order_line.id', 'in', purchase_line_ids)
                ])

                for purchase_order in purchase_orders:
                    if purchase_orders.product_id.is_dropshipping:
                        # Extraer los valores de la respuesta de la API
                        for data in order_data:
                            if data.get('valor') == "1" and data.get('pedido'):
                                # Actualizar el campo api_supplier_order en el purchase.order relacionado
                                purchase_order.write({
                                    'api_supplier_order': data['pedido']
                                })
                                purchase_order.message_post(body=f"Pedido API guardado: {data['pedido']}")
                            else:
                                # Registrar un mensaje de error en el registro de purchase.order
                                purchase_order.message_post(body="No se pudo guardar el pedido. Valor incorrecto.")
                else:
                    # Si no se encuentra el registro de purchase.order
                    _logger.error('No se encontró una relación con purchase.order en account.move.')
            else:
                _logger.error('account_move no está definido.')

        except Exception as e:
            # Manejo de excepciones genéricas, registrar el error sin detener el proceso
            _logger.error(f"Error fetching order from API: {e}")

    def delete_products(self):
        products_to_delete = self.env['product.api.result'].search([])
        products_to_delete.unlink()


class ProductApiCategory(models.Model):
    _name = 'product.category.api'
    _description = 'Product Category API'

    name = fields.Char('Name', required=True)
    codigo_categoria = fields.Integer('Category Code')
    slug = fields.Char('Slug')

class ProductApiSubCategory(models.Model):
    _name = 'product.subcategory.api'
    _description = 'Product Sub Category API'

    codigo_categoria = fields.Char('Category Code')
    codigo_sub_categoria = fields.Integer('Sub Category Code')
    name = fields.Char('Name', required=True)
    slug = fields.Char('Slug')

class ProductApiBrands(models.Model):
    _name = 'product.brands.api'
    _description = 'Product Brands API'

    codigo_marca = fields.Char('Codigo Marca')
    name = fields.Char('Marks')
    codigo_categoria = fields.Char('Codigo Categoría')
    marca_homologada = fields.Char('Marca Homologada')

class ProductApiProduct(models.Model):
    _name = 'product.api.result'

    sku = fields.Char(string='sku',readonly=True)
    partnum = fields.Char(string='Part Number',readonly=True)
    name = fields.Char(string='Name',readonly=True)
    price = fields.Float(string='Price',readonly=True)
    quantity = fields.Char(string='Quantity',readonly=True)
    mark = fields.Char(string='Mark',readonly=True)
    warehouse = fields.Char(string='Warehouse',readonly=True)
    product_api_id = fields.Many2one('call.products.api', string='Product API',readonly=True)
    selected = fields.Boolean(string='Selected', default=False)

    def create_odoo_product(self,update=None):
        for record in self:
            product_template = self.env['product.template'].search([('default_code', '=', record.sku)], limit=1)
            buy_route = self.env.ref('purchase_stock.route_warehouse0_buy')
            dropship_route = self.env.ref('stock_dropshipping.route_drop_shipping')
            # Crear el producto si no existe y está seleccionado
            if not product_template and record.selected:
                # Obtener rutas de compra y dropshipping

                product_template = self.env['product.template'].create({
                    'name': record.name,
                    'default_code': record.sku,
                    # custom_castor_data campos SKU
                    'config_sku' : record.sku,
                    'sku' : record.sku,
                    #
                    'standard_price': record.price,
                    'is_dropshipping': True,
                    'route_ids': [(6, 0, [buy_route.id, dropship_route.id])],  # Asignar rutas
                    'dropshipping_warehouse': record.warehouse,
                    'dropshipping_brand': record.mark
                })

            if product_template:

                product_template.write({
                    'name': record.name,
                    'default_code': record.sku,
                    # custom_castor_data campos SKU
                    'config_sku' : record.sku,
                    'sku' : record.sku,
                    #
                    'standard_price': record.price,
                    'is_dropshipping': True,
                    'route_ids': [(6, 0, [buy_route.id, dropship_route.id])],  # Asignar rutas
                    'dropshipping_warehouse': record.warehouse,
                    'dropshipping_brand': record.mark
                })

                partner_id = self.product_api_id.api_credentials_ids.partner_id.id
                if not partner_id:
                    raise UserError('Selecciona tu proveedor en la búsqueda')

                supplierinfo = self.env['product.supplierinfo'].search([
                    ('product_tmpl_id', '=', product_template.id),
                    ('partner_id', '=', self.product_api_id.api_credentials_ids.partner_id.id)
                ], limit=1)

                if supplierinfo:
                    # Actualizar el precio si el proveedor existe
                    supplierinfo.write({
                        'product_tmpl_id': product_template.id,
                        'partner_id': partner_id,
                        'price': record.price,
                        'quantity_supplier': record.quantity,
                    })
                else:
                    # Crear un nuevo proveedor si no existe
                    self.env['product.supplierinfo'].create({
                        'product_tmpl_id': product_template.id,
                        'partner_id': partner_id,
                        'price': record.price,
                        'quantity_supplier': record.quantity,
                    })