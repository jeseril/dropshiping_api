from odoo import models, fields, api
import requests, ast

class ResCompany(models.Model):
    _inherit = 'res.company'

    api_credentials_ids = fields.One2many('api.credentials', 'company_id', string='API Credentials')

class api_credentials(models.Model):
    _name = "api.credentials"

    name = fields.Char('Nombre del proveedor')
    username = fields.Char(string='Email')
    password = fields.Char(string='Password')
    token = fields.Char(string='Token', readonly=True)
    company_id = fields.Many2one('res.company', string='Company', ondelete='cascade', readonly=True)
    partner_id = fields.Many2one('res.partner', string='Proveedor', ondelete='set null')
    configuration_api_ids = fields.One2many('api.configuration', 'api_credentials_id', string='Configuration')

class configuration_api(models.Model):
    _name = 'api.configuration'

    name= fields.Char(string='Name')
    http_method = fields.Selection([
        ('get', 'GET'),
        ('post', 'POST'),
        ('put', 'PUT'),
        ('delete', 'DELETE'),
    ], string='HTTP Method')
    url_endpoint = fields.Char(string='URL Endpoint')
    params = fields.Char(string='Params')
    authorization_type = fields.Char(string='Authorization Type')

    headers = fields.Char(string='Headers')
    body = fields.Char(string='Body')
    body_is_json = fields.Boolean(string='Body is JSON?')
    api_credentials_id = fields.Many2one('api.credentials', string='API Credentials', readonly=True)
    mps_methods_ids = fields.One2many('api.methods', 'api_configuration_id', string='Configuration')

    key_mapping = fields.Char(string='Key Mapping')

    def write(self, vals):
        res = super(configuration_api, self).write(vals)
        for record in self:
            record.mps_methods_ids.authenticate_api()
        return res

    @api.model
    def cron_authenticate_api(self):
        records = self.search([])
        for record in records:
            record.mps_methods_ids.authenticate_api()